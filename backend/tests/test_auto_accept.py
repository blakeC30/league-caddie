"""
Tests for the auto_accept_requests feature on leagues.

Covers:
  - PATCH /leagues/{league_id} — enable/disable auto_accept_requests
  - Batch-accept pending requests when toggled on
  - Validation: can't enable if pending + approved > member_limit
  - POST /leagues/join/{invite_code} — auto-approved when flag is on
  - POST /leagues/join/{invite_code} — rejected when league is full + auto-accept on
  - GET /leagues/join/{invite_code} — preview includes auto_accept_requests
"""

from datetime import date

from app.models import (
    League,
    LeagueMember,
    LeagueMemberRole,
    LeagueMemberStatus,
    Season,
    User,
)
from app.models.league_purchase import LeaguePurchase
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(db, email: str, display_name: str = "User") -> User:
    user = User(
        email=email,
        password_hash=hash_password("password123"),
        display_name=display_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_league(
    db,
    creator: User,
    name: str = "Auto Accept League",
    auto_accept: bool = False,
    member_limit: int = 20,
) -> League:
    league = League(
        name=name,
        created_by=creator.id,
        auto_accept_requests=auto_accept,
    )
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
    db.add(Season(league_id=league.id, year=date.today().year, is_active=True))
    # Create a purchase so the league is active and has a member_limit.
    db.add(
        LeaguePurchase(
            league_id=league.id,
            season_year=date.today().year,
            tier="standard",
            member_limit=member_limit,
            stripe_customer_id="cus_test",
            stripe_payment_intent_id="pi_test",
            stripe_checkout_session_id="cs_test",
            amount_cents=4999,
            paid_at=db.execute(__import__("sqlalchemy").text("SELECT NOW()")).scalar(),
        )
    )
    db.commit()
    db.refresh(league)
    return league


def _login_user(client, email: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _register_and_login(client, email: str) -> dict:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": "User"},
    )
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _add_pending(db, league: League, user: User):
    db.add(
        LeagueMember(
            league_id=league.id,
            user_id=user.id,
            role=LeagueMemberRole.MEMBER.value,
            status=LeagueMemberStatus.PENDING.value,
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# Toggle auto_accept_requests
# ---------------------------------------------------------------------------


class TestAutoAcceptToggle:
    def test_enable_auto_accept(self, client, db):
        """Manager can enable auto_accept_requests."""
        manager = _make_user(db, "mgr_toggle_on@example.com")
        league = _make_league(db, manager)
        headers = _login_user(client, manager.email)

        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=headers,
            json={"auto_accept_requests": True},
        )
        assert resp.status_code == 200
        assert resp.json()["auto_accept_requests"] is True

    def test_disable_auto_accept(self, client, db):
        """Manager can disable auto_accept_requests."""
        manager = _make_user(db, "mgr_toggle_off@example.com")
        league = _make_league(db, manager, auto_accept=True)
        headers = _login_user(client, manager.email)

        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=headers,
            json={"auto_accept_requests": False},
        )
        assert resp.status_code == 200
        assert resp.json()["auto_accept_requests"] is False

    def test_batch_accepts_pending_on_enable(self, client, db):
        """Enabling auto-accept batch-accepts all pending requests."""
        manager = _make_user(db, "mgr_batch@example.com")
        league = _make_league(db, manager)
        headers = _login_user(client, manager.email)

        # Add pending members
        p1 = _make_user(db, "pending1_batch@example.com")
        p2 = _make_user(db, "pending2_batch@example.com")
        _add_pending(db, league, p1)
        _add_pending(db, league, p2)

        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=headers,
            json={"auto_accept_requests": True},
        )
        assert resp.status_code == 200

        # Verify all are approved
        pending = (
            db.query(LeagueMember)
            .filter_by(league_id=league.id, status=LeagueMemberStatus.PENDING.value)
            .count()
        )
        assert pending == 0

        approved = (
            db.query(LeagueMember)
            .filter_by(league_id=league.id, status=LeagueMemberStatus.APPROVED.value)
            .count()
        )
        assert approved == 3  # manager + 2 pending

    def test_enable_blocked_when_exceeds_limit(self, client, db):
        """Cannot enable auto-accept if batch-accepting would exceed member limit."""
        manager = _make_user(db, "mgr_limit@example.com")
        league = _make_league(db, manager, member_limit=2)  # limit=2, manager already counts as 1
        headers = _login_user(client, manager.email)

        # Add 2 pending members — total would be 3, exceeding limit of 2
        p1 = _make_user(db, "pending1_limit@example.com")
        p2 = _make_user(db, "pending2_limit@example.com")
        _add_pending(db, league, p1)
        _add_pending(db, league, p2)

        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=headers,
            json={"auto_accept_requests": True},
        )
        assert resp.status_code == 422
        assert "Cannot enable auto-accept" in resp.json()["detail"]

    def test_enable_with_zero_pending_succeeds(self, client, db):
        """Enabling auto-accept with no pending requests always succeeds."""
        manager = _make_user(db, "mgr_no_pending@example.com")
        league = _make_league(db, manager, member_limit=2)
        headers = _login_user(client, manager.email)

        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=headers,
            json={"auto_accept_requests": True},
        )
        assert resp.status_code == 200
        assert resp.json()["auto_accept_requests"] is True


# ---------------------------------------------------------------------------
# Join with auto-accept enabled
# ---------------------------------------------------------------------------


class TestJoinAutoAccept:
    def test_join_auto_accepted(self, client, db):
        """Joining a league with auto-accept ON returns approved membership."""
        manager = _make_user(db, "mgr_autojoin@example.com")
        league = _make_league(db, manager, auto_accept=True)

        joiner_headers = _register_and_login(client, "joiner_auto@example.com")
        resp = client.post(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=joiner_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "approved"

    def test_join_rejected_when_full_and_auto_accept(self, client, db):
        """Joining a full league with auto-accept ON returns 422."""
        manager = _make_user(db, "mgr_full_auto@example.com")
        league = _make_league(db, manager, auto_accept=True, member_limit=1)  # manager fills it

        joiner_headers = _register_and_login(client, "joiner_full_auto@example.com")
        resp = client.post(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=joiner_headers,
        )
        assert resp.status_code == 422
        assert "full" in resp.json()["detail"].lower()

    def test_join_without_auto_accept_returns_pending(self, client, db):
        """Joining a league with auto-accept OFF returns pending membership."""
        manager = _make_user(db, "mgr_no_auto@example.com")
        league = _make_league(db, manager, auto_accept=False)

        joiner_headers = _register_and_login(client, "joiner_pending@example.com")
        resp = client.post(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=joiner_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"


# ---------------------------------------------------------------------------
# Preview includes auto_accept_requests
# ---------------------------------------------------------------------------


class TestPreviewAutoAccept:
    def test_preview_shows_auto_accept_false(self, client, db):
        """Preview includes auto_accept_requests=false by default."""
        manager = _make_user(db, "mgr_preview_off@example.com")
        league = _make_league(db, manager)

        visitor_headers = _register_and_login(client, "visitor_preview_off@example.com")
        resp = client.get(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=visitor_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["auto_accept_requests"] is False

    def test_preview_shows_auto_accept_true(self, client, db):
        """Preview includes auto_accept_requests=true when enabled."""
        manager = _make_user(db, "mgr_preview_on@example.com")
        league = _make_league(db, manager, auto_accept=True)

        visitor_headers = _register_and_login(client, "visitor_preview_on@example.com")
        resp = client.get(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=visitor_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["auto_accept_requests"] is True


# ---------------------------------------------------------------------------
# Auto-accept + paused interaction
# ---------------------------------------------------------------------------


class TestAutoAcceptPausedInteraction:
    def test_enable_auto_accept_clears_pending_when_paused(self, client, db):
        """Enabling auto-accept batch-accepts pending requests even when league is paused."""
        manager = _make_user(db, "mgr_paused_aa@example.com")
        league = _make_league(db, manager)
        headers = _login_user(client, manager.email)

        # Pause requests
        client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=headers,
            json={"accepting_requests": False},
        )

        # Add pending member
        p1 = _make_user(db, "pending_paused@example.com")
        _add_pending(db, league, p1)

        # Enable auto-accept — pending should be batch-accepted
        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=headers,
            json={"auto_accept_requests": True},
        )
        assert resp.status_code == 200

        pending = (
            db.query(LeagueMember)
            .filter_by(league_id=league.id, status=LeagueMemberStatus.PENDING.value)
            .count()
        )
        assert pending == 0

        approved = (
            db.query(LeagueMember)
            .filter_by(league_id=league.id, status=LeagueMemberStatus.APPROVED.value)
            .count()
        )
        assert approved == 2  # manager + pending member

    def test_no_pending_requests_remain_after_auto_accept_enabled(self, client, db):
        """After enabling auto-accept, no pending requests should exist."""
        manager = _make_user(db, "mgr_no_pend@example.com")
        league = _make_league(db, manager)
        headers = _login_user(client, manager.email)

        # Add 3 pending members
        for i in range(3):
            u = _make_user(db, f"pend_{i}_nopend@example.com")
            _add_pending(db, league, u)

        # Enable auto-accept
        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=headers,
            json={"auto_accept_requests": True},
        )
        assert resp.status_code == 200

        # Verify: zero pending, all approved
        pending = (
            db.query(LeagueMember)
            .filter_by(league_id=league.id, status=LeagueMemberStatus.PENDING.value)
            .count()
        )
        assert pending == 0

        # Check pending requests endpoint returns empty
        resp = client.get(
            f"/api/v1/leagues/{league.id}/requests",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_paused_auto_accept_league_rejects_new_requests(self, client, db):
        """A paused league with auto-accept ON still blocks new join requests."""
        manager = _make_user(db, "mgr_paused_reject@example.com")
        league = _make_league(db, manager, auto_accept=True)
        headers = _login_user(client, manager.email)

        # Pause requests
        client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=headers,
            json={"accepting_requests": False},
        )

        joiner_headers = _register_and_login(client, "joiner_paused_reject@example.com")
        resp = client.post(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=joiner_headers,
        )
        assert resp.status_code == 403
        assert "not currently accepting" in resp.json()["detail"].lower()
