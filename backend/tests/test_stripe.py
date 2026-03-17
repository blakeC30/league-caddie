"""
Tests for Stripe payment endpoints.

Covers:
  GET  /stripe/pricing                  — public endpoint, no auth
  GET  /leagues/{id}/purchase           — member endpoint, returns null when no purchase
  POST /stripe/create-league-checkout   — validation + webhook handler (create_league branch)
  require_active_purchase               — 402 when unpurchased, bypass for platform admin
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.main import app
from app.models import (
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    LeaguePurchase,
    Season,
    User,
)
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(db, email: str, *, is_platform_admin: bool = False) -> User:
    user = User(
        email=email,
        password_hash=hash_password("password123"),
        display_name="Test",
        is_platform_admin=is_platform_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_league(db, creator: User) -> League:
    league = League(name="Test League", created_by=creator.id)
    db.add(league)
    db.flush()
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=creator.id,
            role=LeagueMemberRole.MANAGER.value,
            status=LeagueMemberStatus.APPROVED.value,
        )
    )
    db.add(Season(league_id=league.id, year=datetime.now(UTC).year, is_active=True))
    db.commit()
    db.refresh(league)
    return league


def _make_purchase(db, league: League, *, tier: str = "elite") -> LeaguePurchase:
    from app.schemas.stripe_schemas import PRICING_TIERS

    info = PRICING_TIERS[tier]
    purchase = LeaguePurchase(
        id=uuid.uuid4(),
        league_id=league.id,
        season_year=datetime.now(UTC).year,
        tier=tier,
        member_limit=info["member_limit"],
        amount_cents=info["amount_cents"],
        paid_at=datetime.now(UTC),
    )
    db.add(purchase)
    db.commit()
    db.refresh(purchase)
    return purchase


def _auth_headers(client, email: str) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert resp.status_code == 200, resp.json()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# GET /stripe/pricing
# ---------------------------------------------------------------------------


class TestPricing:
    def test_returns_four_tiers(self, client):
        resp = client.get("/api/v1/stripe/pricing")
        assert resp.status_code == 200
        tiers = resp.json()
        assert len(tiers) == 4
        names = {t["tier"] for t in tiers}
        assert names == {"starter", "standard", "pro", "elite"}

    def test_each_tier_has_required_fields(self, client):
        resp = client.get("/api/v1/stripe/pricing")
        for tier in resp.json():
            assert "tier" in tier
            assert "member_limit" in tier
            assert "amount_cents" in tier
            assert tier["amount_cents"] > 0
            assert tier["member_limit"] > 0

    def test_no_auth_required(self, client):
        """Pricing is public — no Authorization header needed."""
        resp = client.get("/api/v1/stripe/pricing")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /leagues/{id}/purchase
# ---------------------------------------------------------------------------


class TestGetLeaguePurchase:
    def test_returns_null_when_no_purchase(self, client, db):
        user = _make_user(db, "buyer@example.com")
        league = _make_league(db, user)
        headers = _auth_headers(client, "buyer@example.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/purchase", headers=headers)
        assert resp.status_code == 200
        assert resp.json() is None

    def test_returns_purchase_when_exists(self, client, db):
        user = _make_user(db, "buyer2@example.com")
        league = _make_league(db, user)
        _make_purchase(db, league, tier="standard")
        headers = _auth_headers(client, "buyer2@example.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/purchase", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["tier"] == "standard"
        assert data["member_limit"] == 50
        assert data["paid_at"] is not None

    def test_requires_auth(self, client, db):
        user = _make_user(db, "buyer3@example.com")
        league = _make_league(db, user)

        resp = client.get(f"/api/v1/leagues/{league.id}/purchase")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /stripe/create-checkout-session — validation paths (no Stripe API call)
# ---------------------------------------------------------------------------


class TestCreateCheckoutSessionValidation:
    def test_invalid_tier_returns_422(self, client, db):
        user = _make_user(db, "checkout1@example.com")
        _make_league(db, user)
        headers = _auth_headers(client, "checkout1@example.com")
        league = db.query(League).filter_by(created_by=user.id).first()

        resp = client.post(
            "/api/v1/stripe/create-checkout-session",
            json={"league_id": str(league.id), "tier": "invalid_tier"},
            headers=headers,
        )
        assert resp.status_code == 422
        assert "Invalid tier" in resp.json()["detail"]

    def test_league_not_found_returns_404(self, client, db):
        _make_user(db, "checkout2@example.com")
        headers = _auth_headers(client, "checkout2@example.com")

        resp = client.post(
            "/api/v1/stripe/create-checkout-session",
            json={"league_id": str(uuid.uuid4()), "tier": "starter"},
            headers=headers,
        )
        assert resp.status_code == 404

    def test_non_manager_returns_403(self, client, db):
        manager = _make_user(db, "manager_co@example.com")
        member = _make_user(db, "member_co@example.com")
        league = _make_league(db, manager)
        # Add member as a regular member
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()
        headers = _auth_headers(client, "member_co@example.com")

        resp = client.post(
            "/api/v1/stripe/create-checkout-session",
            json={"league_id": str(league.id), "tier": "starter"},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_requires_auth(self, client, db):
        resp = client.post(
            "/api/v1/stripe/create-checkout-session",
            json={"league_id": str(uuid.uuid4()), "tier": "starter"},
        )
        assert resp.status_code == 401

    def test_upgrade_to_lower_tier_returns_422(self, client, db):
        user = _make_user(db, "upgrade1@example.com")
        league = _make_league(db, user)
        _make_purchase(db, league, tier="pro")
        headers = _auth_headers(client, "upgrade1@example.com")

        # Trying to "upgrade" to starter (lower than pro) should fail
        resp = client.post(
            "/api/v1/stripe/create-checkout-session",
            json={"league_id": str(league.id), "tier": "starter", "upgrade": True},
            headers=headers,
        )
        assert resp.status_code == 422
        assert "higher" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /stripe/create-league-checkout — validation paths (no Stripe API call)
# ---------------------------------------------------------------------------


class TestCreateLeagueCheckoutValidation:
    def test_invalid_tier_returns_422(self, client, db):
        _make_user(db, "newleague1@example.com")
        headers = _auth_headers(client, "newleague1@example.com")

        resp = client.post(
            "/api/v1/stripe/create-league-checkout",
            json={"name": "My League", "no_pick_penalty": 0, "tier": "bogus"},
            headers=headers,
        )
        assert resp.status_code == 422
        assert "Invalid tier" in resp.json()["detail"]

    def test_requires_auth(self, client):
        resp = client.post(
            "/api/v1/stripe/create-league-checkout",
            json={"name": "My League", "no_pick_penalty": 0, "tier": "starter"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# _handle_checkout_complete — create_league branch (called directly, no Stripe)
# ---------------------------------------------------------------------------


class TestHandleCheckoutCompleteCreateLeague:
    def test_creates_league_and_related_rows(self, db):
        from app.models import League, LeagueMember, LeaguePurchase, LeaguePurchaseEvent, Season
        from app.routers.stripe_router import _handle_checkout_complete

        user = _make_user(db, "webhook1@example.com")
        pending_id = uuid.uuid4()
        current_year = datetime.now(UTC).year

        session = {
            "id": "cs_test_123",
            "customer": "cus_test",
            "payment_intent": "pi_test",
            "amount_total": 5000,
            "metadata": {
                "action": "create_league",
                "pending_league_id": str(pending_id),
                "league_name": "Webhook League",
                "no_pick_penalty": "10000",
                "user_id": str(user.id),
                "tier": "starter",
                "season_year": str(current_year),
            },
        }

        _handle_checkout_complete(session, db)

        league = db.query(League).filter_by(id=pending_id).first()
        assert league is not None
        assert league.name == "Webhook League"
        assert league.no_pick_penalty == 10000

        season = db.query(Season).filter_by(league_id=pending_id).first()
        assert season is not None
        assert season.year == current_year

        member = db.query(LeagueMember).filter_by(league_id=pending_id, user_id=user.id).first()
        assert member is not None
        assert member.role == "manager"

        purchase = db.query(LeaguePurchase).filter_by(league_id=pending_id).first()
        assert purchase is not None
        assert purchase.tier == "starter"
        assert purchase.paid_at is not None

        event = db.query(LeaguePurchaseEvent).filter_by(league_id=pending_id).first()
        assert event is not None
        assert event.event_type == "purchase"

    def test_missing_metadata_logs_and_returns(self, db):
        from app.routers.stripe_router import _handle_checkout_complete

        session = {
            "id": "cs_test_bad",
            "customer": "cus_test",
            "payment_intent": "pi_test",
            "amount_total": 5000,
            "metadata": {
                "action": "create_league",
                # missing pending_league_id, league_name, user_id
                "tier": "starter",
                "season_year": str(datetime.now(UTC).year),
            },
        }
        # Should return without raising
        _handle_checkout_complete(session, db)


# ---------------------------------------------------------------------------
# require_active_purchase — 402 gating (tested directly via standings endpoint,
# using a client that does NOT bypass require_active_purchase)
# ---------------------------------------------------------------------------


class TestRequireActivePurchase:
    @pytest.fixture
    def gated_client(self, db):
        """TestClient that does NOT bypass require_active_purchase."""
        from fastapi.testclient import TestClient

        from app.database import get_db
        from tests.conftest import TestingSessionLocal

        def _override_get_db():
            s = TestingSessionLocal()
            try:
                yield s
            finally:
                s.close()

        # Remove the bypass — only override get_db
        # Temporarily set only get_db (no purchase bypass)
        original = app.dependency_overrides.copy()
        app.dependency_overrides.clear()
        app.dependency_overrides[get_db] = _override_get_db
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)

    def test_unpurchased_league_returns_402(self, gated_client, db):
        user = _make_user(db, "gate1@example.com")
        _make_league(db, user)

        resp = gated_client.post(
            "/api/v1/auth/login",
            json={"email": "gate1@example.com", "password": "password123"},
        )
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        league = db.query(League).filter_by(created_by=user.id).first()
        resp = gated_client.get(f"/api/v1/leagues/{league.id}/standings", headers=headers)
        assert resp.status_code == 402
        assert "season pass" in resp.json()["detail"].lower()

    def test_platform_admin_league_bypasses_gate(self, gated_client, db):
        admin = _make_user(db, "admin_gate@example.com", is_platform_admin=True)
        _make_league(db, admin)

        resp = gated_client.post(
            "/api/v1/auth/login",
            json={"email": "admin_gate@example.com", "password": "password123"},
        )
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        league = db.query(League).filter_by(created_by=admin.id).first()
        # standings returns 404 (no active season? no — we created one) … actually 200
        resp = gated_client.get(f"/api/v1/leagues/{league.id}/standings", headers=headers)
        # Platform admin bypass means we get through the gate (200, not 402)
        assert resp.status_code == 200

    def test_purchased_league_allows_access(self, gated_client, db):
        user = _make_user(db, "gate2@example.com")
        league = _make_league(db, user)
        _make_purchase(db, league)

        resp = gated_client.post(
            "/api/v1/auth/login",
            json={"email": "gate2@example.com", "password": "password123"},
        )
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = gated_client.get(f"/api/v1/leagues/{league.id}/standings", headers=headers)
        assert resp.status_code == 200
