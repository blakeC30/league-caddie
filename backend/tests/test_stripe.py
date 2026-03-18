"""
Tests for Stripe payment endpoints.

Covers:
  GET  /stripe/pricing                       — public endpoint, no auth
  GET  /leagues/{id}/purchase                — member endpoint, returns null when no purchase
  GET  /leagues/{id}/purchase/events         — manager endpoint, payment history
  POST /stripe/create-league-checkout        — validation + webhook handler (create_league branch)
  POST /stripe/webhook                       — signature validation + failure recording
  require_active_purchase                    — 402 when unpurchased, bypass for platform admin
  _handle_checkout_complete                  — edge cases, upgrade/renew branch, idempotency
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.main import app
from app.models import (
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    LeaguePurchase,
    LeaguePurchaseEvent,
    Season,
    StripeWebhookFailure,
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
# GET /leagues/{id}/purchase/events
# ---------------------------------------------------------------------------


def _make_purchase_event(
    db,
    league: League,
    *,
    tier: str = "starter",
    amount_cents: int = 5000,
    event_type: str = "purchase",
    paid_at: datetime | None = None,
) -> LeaguePurchaseEvent:
    event = LeaguePurchaseEvent(
        league_id=league.id,
        season_year=datetime.now(UTC).year,
        tier=tier,
        member_limit=20,
        amount_cents=amount_cents,
        event_type=event_type,
        paid_at=paid_at or datetime.now(UTC),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


class TestGetLeaguePurchaseEvents:
    def test_returns_empty_list_when_no_events(self, client, db):
        user = _make_user(db, "evts_empty@example.com")
        league = _make_league(db, user)
        _make_purchase(db, league)
        headers = _auth_headers(client, "evts_empty@example.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/purchase/events", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_single_purchase_event(self, client, db):
        user = _make_user(db, "evts_one@example.com")
        league = _make_league(db, user)
        _make_purchase(db, league, tier="standard")
        _make_purchase_event(db, league, tier="standard", amount_cents=9000, event_type="purchase")
        headers = _auth_headers(client, "evts_one@example.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/purchase/events", headers=headers)
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 1
        assert events[0]["tier"] == "standard"
        assert events[0]["amount_cents"] == 9000
        assert events[0]["event_type"] == "purchase"
        assert events[0]["paid_at"] is not None
        assert "id" in events[0]

    def test_returns_events_in_chronological_order(self, client, db):
        from datetime import timedelta

        user = _make_user(db, "evts_order@example.com")
        league = _make_league(db, user)
        _make_purchase(db, league, tier="pro")
        now = datetime.now(UTC)
        _make_purchase_event(
            db,
            league,
            tier="starter",
            amount_cents=5000,
            event_type="purchase",
            paid_at=now - timedelta(days=7),
        )
        _make_purchase_event(
            db,
            league,
            tier="pro",
            amount_cents=10000,
            event_type="upgrade",
            paid_at=now,
        )
        headers = _auth_headers(client, "evts_order@example.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/purchase/events", headers=headers)
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 2
        assert events[0]["event_type"] == "purchase"  # oldest first
        assert events[1]["event_type"] == "upgrade"

    def test_upgrade_event_has_correct_amount(self, client, db):
        """Upgrade events store the prorated charge, not the full tier price."""
        user = _make_user(db, "evts_upgrade@example.com")
        league = _make_league(db, user)
        _make_purchase(db, league, tier="pro")
        _make_purchase_event(
            db,
            league,
            tier="pro",
            amount_cents=10000,
            event_type="upgrade",
        )
        headers = _auth_headers(client, "evts_upgrade@example.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/purchase/events", headers=headers)
        assert resp.status_code == 200
        event = resp.json()[0]
        assert event["event_type"] == "upgrade"
        assert event["amount_cents"] == 10000

    def test_requires_auth(self, client, db):
        user = _make_user(db, "evts_noauth@example.com")
        league = _make_league(db, user)

        resp = client.get(f"/api/v1/leagues/{league.id}/purchase/events")
        assert resp.status_code == 401

    def test_requires_manager_role(self, client, db):
        """Regular members must receive 403 — billing history is manager-only."""
        manager = _make_user(db, "evts_mgr@example.com")
        member = _make_user(db, "evts_member@example.com")
        league = _make_league(db, manager)
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()
        _make_purchase_event(db, league, tier="starter", amount_cents=5000)
        headers = _auth_headers(client, "evts_member@example.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/purchase/events", headers=headers)
        assert resp.status_code == 403

    def test_non_member_returns_403(self, client, db):
        """Users who are not league members get 403 from require_league_manager."""
        owner = _make_user(db, "evts_owner@example.com")
        _make_user(db, "evts_outsider@example.com")
        league = _make_league(db, owner)
        headers = _auth_headers(client, "evts_outsider@example.com")

        resp = client.get(f"/api/v1/leagues/{league.id}/purchase/events", headers=headers)
        assert resp.status_code == 403

    def test_does_not_return_events_from_another_league(self, client, db):
        manager = _make_user(db, "evts_iso@example.com")
        league_a = _make_league(db, manager)
        league_b = _make_league(db, manager)
        _make_purchase(db, league_a)
        _make_purchase_event(db, league_b, tier="elite", amount_cents=25000)
        headers = _auth_headers(client, "evts_iso@example.com")

        resp = client.get(f"/api/v1/leagues/{league_a.id}/purchase/events", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []  # league_b's event must not appear


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

    def test_missing_metadata_raises(self, db):
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
        with pytest.raises(ValueError, match="missing metadata"):
            _handle_checkout_complete(session, db)


# ---------------------------------------------------------------------------
# require_active_purchase — 402 gating (tested directly via standings endpoint,
# using a client that does NOT bypass require_active_purchase)
# ---------------------------------------------------------------------------


class TestRequireActivePurchase:
    @pytest.fixture
    def gated_client(self, db, session_factory):
        """TestClient that does NOT bypass require_active_purchase."""
        from fastapi.testclient import TestClient

        from app.database import get_db

        def _override_get_db():
            s = session_factory()
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


# ---------------------------------------------------------------------------
# require_active_purchase — platform admin user bypass
# (additional test: current user is admin, not just league creator)
# ---------------------------------------------------------------------------


class TestRequireActivePurchasePlatformAdminUser:
    @pytest.fixture
    def gated_client(self, db, session_factory):
        """TestClient that does NOT bypass require_active_purchase."""
        from fastapi.testclient import TestClient

        from app.database import get_db

        def _override_get_db():
            s = session_factory()
            try:
                yield s
            finally:
                s.close()

        original = app.dependency_overrides.copy()
        app.dependency_overrides.clear()
        app.dependency_overrides[get_db] = _override_get_db
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)

    def test_platform_admin_user_bypasses_gate_for_others_league(self, gated_client, db):
        """
        A platform admin visiting another user's unpurchased league must get
        through the gate — the bypass applies to the current user's admin status,
        not just the league creator's status.
        """
        regular = _make_user(db, "regular_creator@example.com")
        admin = _make_user(db, "admin_visitor@example.com", is_platform_admin=True)
        league = _make_league(db, regular)  # created by non-admin, no purchase

        # Add the platform admin as a member so require_league_member passes
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=admin.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        resp = gated_client.post(
            "/api/v1/auth/login",
            json={"email": "admin_visitor@example.com", "password": "password123"},
        )
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = gated_client.get(f"/api/v1/leagues/{league.id}/standings", headers=headers)
        # Platform admin bypass → through the gate (200, not 402)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /stripe/webhook — endpoint-level tests (signature validation + failure recording)
# ---------------------------------------------------------------------------


class TestStripeWebhookEndpoint:
    def test_missing_signature_header_returns_400(self, client):
        resp = client.post(
            "/api/v1/stripe/webhook",
            content=b'{"type":"checkout.session.completed"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400
        assert "Missing" in resp.json()["detail"]

    def test_invalid_signature_returns_400(self, client):
        import stripe as stripe_lib

        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe_lib.error.SignatureVerificationError("bad sig", "sig"),
        ):
            resp = client.post(
                "/api/v1/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=bad"},
            )
        assert resp.status_code == 400
        assert "Invalid" in resp.json()["detail"]

    def test_non_checkout_event_returns_200_received(self, client):
        """Events other than checkout.session.completed must be acknowledged but ignored."""
        mock_event = {"type": "payment_intent.succeeded", "data": {"object": {}}}
        with patch("stripe.Webhook.construct_event", return_value=mock_event):
            resp = client.post(
                "/api/v1/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=mock"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"received": True}

    def test_handler_exception_creates_webhook_failure_row(self, client, db):
        """
        When _handle_checkout_complete raises, the webhook handler must record
        the failure so admins can retry it without losing the payload.
        """
        session_obj = {
            "id": "cs_exploding",
            "metadata": {"tier": "starter", "season_year": "2026"},
        }
        mock_event = {"type": "checkout.session.completed", "data": {"object": session_obj}}

        with (
            patch("stripe.Webhook.construct_event", return_value=mock_event),
            patch(
                "app.routers.stripe_router._handle_checkout_complete",
                side_effect=RuntimeError("Unexpected DB error"),
            ),
        ):
            resp = client.post(
                "/api/v1/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=mock"},
            )

        assert resp.status_code == 500
        failure = (
            db.query(StripeWebhookFailure)
            .filter_by(stripe_checkout_session_id="cs_exploding")
            .first()
        )
        assert failure is not None
        assert "Unexpected DB error" in failure.error_message

    def test_successful_checkout_returns_200_received(self, client, db):
        current_year = datetime.now(UTC).year
        user = _make_user(db, "webhookuser@example.com")
        pending_id = uuid.uuid4()
        session_obj = {
            "id": "cs_success_999",
            "customer": "cus_test",
            "payment_intent": "pi_test_999",
            "amount_total": 5000,
            "metadata": {
                "action": "create_league",
                "pending_league_id": str(pending_id),
                "league_name": "Webhook Test League",
                "no_pick_penalty": "0",
                "user_id": str(user.id),
                "tier": "starter",
                "season_year": str(current_year),
            },
        }
        mock_event = {"type": "checkout.session.completed", "data": {"object": session_obj}}

        with patch("stripe.Webhook.construct_event", return_value=mock_event):
            resp = client.post(
                "/api/v1/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "t=1,v1=mock"},
            )

        assert resp.status_code == 200
        assert resp.json() == {"received": True}


# ---------------------------------------------------------------------------
# _handle_checkout_complete — additional edge cases
# ---------------------------------------------------------------------------


class TestHandleCheckoutCompleteEdgeCases:
    def test_missing_tier_raises(self, db):
        from app.routers.stripe_router import _handle_checkout_complete

        session = {
            "id": "cs_no_tier",
            "metadata": {"season_year": "2026"},  # no tier
        }
        with pytest.raises(ValueError, match="missing required metadata"):
            _handle_checkout_complete(session, db)

        from app.models import League

        assert db.query(League).count() == 0

    def test_unknown_tier_raises(self, db):
        from app.routers.stripe_router import _handle_checkout_complete

        session = {
            "id": "cs_bad_tier",
            "metadata": {"tier": "diamond", "season_year": "2026"},
        }
        with pytest.raises(ValueError, match="unknown tier"):
            _handle_checkout_complete(session, db)

    def test_invalid_season_year_raises(self, db):
        from app.routers.stripe_router import _handle_checkout_complete

        session = {
            "id": "cs_bad_year",
            "metadata": {"tier": "starter", "season_year": "not_a_year"},
        }
        with pytest.raises(ValueError, match="invalid season_year"):
            _handle_checkout_complete(session, db)

        from app.models import League

        assert db.query(League).count() == 0

    def test_idempotency_second_call_with_same_session_is_noop(self, db):
        """
        Stripe retries webhooks on timeout.  Calling _handle_checkout_complete
        twice with the same checkout_session_id must produce exactly one League
        and one LeaguePurchaseEvent row — not two.
        """
        from app.models import League, LeaguePurchaseEvent
        from app.routers.stripe_router import _handle_checkout_complete

        user = _make_user(db, "idempotent@example.com")
        pending_id = uuid.uuid4()
        current_year = datetime.now(UTC).year
        session = {
            "id": "cs_idempotent_123",
            "customer": "cus_test",
            "payment_intent": "pi_idempotent",
            "amount_total": 5000,
            "metadata": {
                "action": "create_league",
                "pending_league_id": str(pending_id),
                "league_name": "Idempotent League",
                "no_pick_penalty": "0",
                "user_id": str(user.id),
                "tier": "starter",
                "season_year": str(current_year),
            },
        }

        _handle_checkout_complete(session, db)
        _handle_checkout_complete(session, db)  # second call must be a no-op

        assert db.query(League).filter_by(id=pending_id).count() == 1
        assert (
            db.query(LeaguePurchaseEvent)
            .filter_by(stripe_checkout_session_id="cs_idempotent_123")
            .count()
            == 1
        )

    def test_amount_total_zero_stored_as_zero(self, db):
        """A 100% coupon results in amount_total=0 — must be stored as 0, not replaced with list
        price."""
        from app.models import LeaguePurchase
        from app.routers.stripe_router import _handle_checkout_complete

        user = _make_user(db, "coupon@example.com")
        pending_id = uuid.uuid4()
        current_year = datetime.now(UTC).year
        session = {
            "id": "cs_coupon_100",
            "customer": "cus_coupon",
            "payment_intent": "pi_coupon",
            "amount_total": 0,  # 100% discount applied
            "metadata": {
                "action": "create_league",
                "pending_league_id": str(pending_id),
                "league_name": "Free League",
                "no_pick_penalty": "0",
                "user_id": str(user.id),
                "tier": "starter",
                "season_year": str(current_year),
            },
        }

        _handle_checkout_complete(session, db)

        purchase = db.query(LeaguePurchase).filter_by(league_id=pending_id).first()
        assert purchase is not None
        assert purchase.amount_cents == 0  # 0, not PRICING_TIERS["starter"]["amount_cents"]

    def test_amount_total_missing_falls_back_to_list_price(self, db):
        """When amount_total is absent (unexpected Stripe API change), fall back to list price."""
        from app.models import LeaguePurchase
        from app.routers.stripe_router import _handle_checkout_complete
        from app.schemas.stripe_schemas import PRICING_TIERS

        user = _make_user(db, "noamount@example.com")
        pending_id = uuid.uuid4()
        current_year = datetime.now(UTC).year
        session = {
            "id": "cs_no_amount",
            "customer": "cus_noamount",
            "payment_intent": "pi_noamount",
            # amount_total intentionally absent
            "metadata": {
                "action": "create_league",
                "pending_league_id": str(pending_id),
                "league_name": "No Amount League",
                "no_pick_penalty": "0",
                "user_id": str(user.id),
                "tier": "pro",
                "season_year": str(current_year),
            },
        }

        _handle_checkout_complete(session, db)

        purchase = db.query(LeaguePurchase).filter_by(league_id=pending_id).first()
        assert purchase is not None
        assert purchase.amount_cents == PRICING_TIERS["pro"]["amount_cents"]

    def test_empty_league_name_after_strip_raises(self, db):
        from app.models import League
        from app.routers.stripe_router import _handle_checkout_complete

        user = _make_user(db, "blankname@example.com")
        current_year = datetime.now(UTC).year
        session = {
            "id": "cs_blank_name",
            "metadata": {
                "action": "create_league",
                "pending_league_id": str(uuid.uuid4()),
                "league_name": "   ",  # only whitespace
                "no_pick_penalty": "0",
                "user_id": str(user.id),
                "tier": "starter",
                "season_year": str(current_year),
            },
        }

        with pytest.raises(ValueError, match="empty league_name"):
            _handle_checkout_complete(session, db)

        assert db.query(League).count() == 0

    def test_invalid_pending_league_id_uuid_raises(self, db):
        from app.models import League
        from app.routers.stripe_router import _handle_checkout_complete

        user = _make_user(db, "baduuid@example.com")
        current_year = datetime.now(UTC).year
        session = {
            "id": "cs_bad_uuid",
            "metadata": {
                "action": "create_league",
                "pending_league_id": "not-a-uuid",
                "league_name": "Bad UUID League",
                "no_pick_penalty": "0",
                "user_id": str(user.id),
                "tier": "starter",
                "season_year": str(current_year),
            },
        }

        with pytest.raises(ValueError, match="invalid metadata"):
            _handle_checkout_complete(session, db)

        assert db.query(League).count() == 0

    def test_user_not_found_raises(self, db):
        from app.models import League
        from app.routers.stripe_router import _handle_checkout_complete

        current_year = datetime.now(UTC).year
        session = {
            "id": "cs_no_user",
            "metadata": {
                "action": "create_league",
                "pending_league_id": str(uuid.uuid4()),
                "league_name": "Ghost League",
                "no_pick_penalty": "0",
                "user_id": str(uuid.uuid4()),  # user that doesn't exist
                "tier": "starter",
                "season_year": str(current_year),
            },
        }

        with pytest.raises(ValueError, match="user.*not found"):
            _handle_checkout_complete(session, db)

        assert db.query(League).count() == 0

    def test_duplicate_pending_league_id_skips_creation(self, db):
        """
        If a league with pending_league_id already exists (e.g. a different
        Stripe session carried the same UUID), the handler must skip creation
        rather than raising a PK conflict.
        """
        from app.models import League
        from app.routers.stripe_router import _handle_checkout_complete

        user = _make_user(db, "collision@example.com")
        existing_id = uuid.uuid4()
        current_year = datetime.now(UTC).year

        # Pre-create the league to simulate the collision
        db.add(League(id=existing_id, name="Existing League", created_by=user.id))
        db.commit()

        session = {
            "id": "cs_collision",
            "customer": "cus_col",
            "payment_intent": "pi_col",
            "amount_total": 5000,
            "metadata": {
                "action": "create_league",
                "pending_league_id": str(existing_id),  # reuse the existing UUID
                "league_name": "Duplicate League",
                "no_pick_penalty": "0",
                "user_id": str(user.id),
                "tier": "starter",
                "season_year": str(current_year),
            },
        }

        _handle_checkout_complete(session, db)  # must not raise

        # Still only one league with this ID
        assert db.query(League).filter_by(id=existing_id).count() == 1
        assert db.query(League).filter_by(name="Duplicate League").count() == 0


# ---------------------------------------------------------------------------
# _handle_checkout_complete — upgrade/renew branch
# ---------------------------------------------------------------------------


class TestHandleCheckoutCompleteUpgradeRenew:
    def _base_session(self, league_id: uuid.UUID, tier: str = "pro") -> dict:
        return {
            "id": f"cs_upgrade_{uuid.uuid4().hex[:8]}",
            "customer": "cus_upgrade",
            "payment_intent": f"pi_upgrade_{uuid.uuid4().hex[:8]}",
            "amount_total": 9000,
            "metadata": {
                "league_id": str(league_id),
                "tier": tier,
                "season_year": str(datetime.now(UTC).year),
                # no 'action' key → upgrade/renew branch
            },
        }

    def test_missing_league_id_in_metadata_raises(self, db):
        from app.models import LeaguePurchase
        from app.routers.stripe_router import _handle_checkout_complete

        session = {
            "id": "cs_no_lid",
            "metadata": {"tier": "starter", "season_year": "2026"},  # no league_id
        }
        with pytest.raises(ValueError, match="missing league_id"):
            _handle_checkout_complete(session, db)
        assert db.query(LeaguePurchase).count() == 0

    def test_invalid_league_id_uuid_raises(self, db):
        from app.models import LeaguePurchase
        from app.routers.stripe_router import _handle_checkout_complete

        session = {
            "id": "cs_bad_lid",
            "metadata": {
                "league_id": "not-a-uuid",
                "tier": "starter",
                "season_year": "2026",
            },
        }
        with pytest.raises(ValueError, match="invalid league_id"):
            _handle_checkout_complete(session, db)
        assert db.query(LeaguePurchase).count() == 0

    def test_league_not_found_raises(self, db):
        from app.models import LeaguePurchase
        from app.routers.stripe_router import _handle_checkout_complete

        session = {
            "id": "cs_ghost_league",
            "metadata": {
                "league_id": str(uuid.uuid4()),  # non-existent league
                "tier": "starter",
                "season_year": str(datetime.now(UTC).year),
            },
        }
        with pytest.raises(ValueError, match="league.*not found"):
            _handle_checkout_complete(session, db)
        assert db.query(LeaguePurchase).count() == 0

    def test_creates_new_purchase_when_none_exists(self, db):
        """First-time payment for an existing league creates a LeaguePurchase row."""
        from app.models import LeaguePurchase, LeaguePurchaseEvent
        from app.routers.stripe_router import _handle_checkout_complete

        user = _make_user(db, "firstpay@example.com")
        league = _make_league(db, user)

        session = self._base_session(league.id, tier="standard")
        session["id"] = "cs_firstpay"
        session["payment_intent"] = "pi_firstpay"

        _handle_checkout_complete(session, db)

        purchase = db.query(LeaguePurchase).filter_by(league_id=league.id).first()
        assert purchase is not None
        assert purchase.tier == "standard"
        assert purchase.paid_at is not None
        assert purchase.amount_cents == 9000

        event = db.query(LeaguePurchaseEvent).filter_by(league_id=league.id).first()
        assert event is not None

    def test_upgrades_existing_purchase(self, db):
        """A second payment for the same league+year updates tier and member_limit."""
        from app.models import LeaguePurchase
        from app.routers.stripe_router import _handle_checkout_complete
        from app.schemas.stripe_schemas import PRICING_TIERS

        user = _make_user(db, "upgrader@example.com")
        league = _make_league(db, user)
        _make_purchase(db, league, tier="starter")

        session = self._base_session(league.id, tier="pro")
        session["id"] = "cs_upgrade_pro"
        session["payment_intent"] = "pi_upgrade_pro"
        session["amount_total"] = 10000  # prorated charge

        _handle_checkout_complete(session, db)

        purchase = db.query(LeaguePurchase).filter_by(league_id=league.id).first()
        assert purchase.tier == "pro"
        assert purchase.member_limit == PRICING_TIERS["pro"]["member_limit"]
        # Stores what Stripe actually charged, not the list price
        assert purchase.amount_cents == 10000

    def test_upgrade_creates_purchase_event_row(self, db):
        """Every completed checkout appends an audit row to league_purchase_events."""
        from app.models import LeaguePurchaseEvent
        from app.routers.stripe_router import _handle_checkout_complete

        user = _make_user(db, "auditrow@example.com")
        league = _make_league(db, user)

        session = self._base_session(league.id, tier="elite")
        session["id"] = "cs_audit_elite"
        session["payment_intent"] = "pi_audit_elite"

        _handle_checkout_complete(session, db)

        events = db.query(LeaguePurchaseEvent).filter_by(league_id=league.id).all()
        assert len(events) == 1
        assert events[0].tier == "elite"
        assert events[0].stripe_checkout_session_id == "cs_audit_elite"
