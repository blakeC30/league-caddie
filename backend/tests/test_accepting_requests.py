"""
Tests for the accepting_requests flag on leagues.

Covers:
  - GET /leagues/join/{invite_code}  — preview includes accepting_requests field
  - POST /leagues/join/{invite_code} — blocked (403) when accepting_requests=False
  - PATCH /leagues/{league_id}       — manager can toggle accepting_requests
  - Users with existing pending requests can still see their status when flag is off
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
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers (mirrors test_leagues.py convention)
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
    name: str = "Test League",
    accepting_requests: bool = True,
) -> League:
    league = League(
        name=name,
        created_by=creator.id,
        accepting_requests=accepting_requests,
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
    db.commit()
    db.refresh(league)
    return league


def _register_and_login(client, email: str) -> dict:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": "User"},
    )
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _login_user(client, user_email: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": user_email, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# Preview endpoint — accepting_requests field
# ---------------------------------------------------------------------------


class TestJoinPreviewAcceptingRequests:
    def test_preview_shows_accepting_true_by_default(self, client, db):
        """New leagues default to accepting_requests=True."""
        manager = _make_user(db, "manager_default@example.com")
        league = _make_league(db, manager)

        visitor_headers = _register_and_login(client, "visitor_default@example.com")
        resp = client.get(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=visitor_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["accepting_requests"] is True

    def test_preview_shows_accepting_false_when_paused(self, client, db):
        """Preview correctly reflects accepting_requests=False."""
        manager = _make_user(db, "manager_paused@example.com")
        league = _make_league(db, manager, accepting_requests=False)

        visitor_headers = _register_and_login(client, "visitor_paused@example.com")
        resp = client.get(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=visitor_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["accepting_requests"] is False

    def test_preview_includes_user_status_when_pending_and_not_accepting(self, client, db):
        """
        A user with an existing pending request can still see their status
        (user_status = "pending") even when accepting_requests=False.
        """
        manager = _make_user(db, "manager_pend@example.com")
        league = _make_league(db, manager)

        # User submits a request while the league is open.
        requester = _make_user(db, "requester_pend@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=requester.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        # Manager closes the league.
        league.accepting_requests = False
        db.commit()

        requester_headers = _login_user(client, "requester_pend@example.com")
        resp = client.get(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=requester_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepting_requests"] is False
        assert data["user_status"] == "pending"

    def test_preview_user_status_none_for_unknown_visitor(self, client, db):
        """user_status is null for visitors with no existing relationship."""
        manager = _make_user(db, "manager_null@example.com")
        league = _make_league(db, manager)

        visitor_headers = _register_and_login(client, "visitor_null@example.com")
        resp = client.get(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=visitor_headers,
        )
        assert resp.json()["user_status"] is None


# ---------------------------------------------------------------------------
# Join POST endpoint — blocked when not accepting
# ---------------------------------------------------------------------------


class TestJoinRequestBlockedWhenNotAccepting:
    def test_join_returns_403_when_not_accepting(self, client, db):
        """POST /leagues/join/{code} returns 403 when accepting_requests=False."""
        manager = _make_user(db, "manager_block@example.com")
        league = _make_league(db, manager, accepting_requests=False)

        visitor_headers = _register_and_login(client, "visitor_block@example.com")
        resp = client.post(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=visitor_headers,
        )
        assert resp.status_code == 403
        assert "not currently accepting" in resp.json()["detail"].lower()

    def test_join_succeeds_when_accepting(self, client, db):
        """POST /leagues/join/{code} returns 201 when accepting_requests=True."""
        manager = _make_user(db, "manager_open@example.com")
        league = _make_league(db, manager, accepting_requests=True)

        visitor_headers = _register_and_login(client, "visitor_open@example.com")
        resp = client.post(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=visitor_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"

    def test_already_pending_user_blocked_from_duplicate_request(self, client, db):
        """A user with an existing pending request gets 409, not a 403 or duplicate row."""
        manager = _make_user(db, "manager_dup@example.com")
        league = _make_league(db, manager)

        requester = _make_user(db, "requester_dup@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=requester.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        db.commit()

        requester_headers = _login_user(client, "requester_dup@example.com")
        resp = client.post(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=requester_headers,
        )
        # 409 Conflict — existing-member check fires before the accepting_requests check.
        assert resp.status_code == 409

    def test_invalid_invite_code_returns_404_regardless(self, client, db):
        """Unknown invite codes return 404 even when not accepting."""
        visitor_headers = _register_and_login(client, "visitor_404@example.com")
        resp = client.post(
            "/api/v1/leagues/join/completelyfakecode",
            headers=visitor_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /leagues/{id} — manager toggles accepting_requests
# ---------------------------------------------------------------------------


class TestUpdateLeagueAcceptingRequests:
    def test_manager_can_disable_accepting_requests(self, client, db):
        """Manager sets accepting_requests=False via PATCH."""
        manager = _make_user(db, "manager_patch@example.com")
        league = _make_league(db, manager)
        assert league.accepting_requests is True

        headers = _login_user(client, "manager_patch@example.com")
        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=headers,
            json={"accepting_requests": False},
        )
        assert resp.status_code == 200
        assert resp.json()["accepting_requests"] is False

    def test_manager_can_re_enable_accepting_requests(self, client, db):
        """Manager can flip accepting_requests back to True after disabling it."""
        manager = _make_user(db, "manager_reopen@example.com")
        league = _make_league(db, manager, accepting_requests=False)

        headers = _login_user(client, "manager_reopen@example.com")
        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=headers,
            json={"accepting_requests": True},
        )
        assert resp.status_code == 200
        assert resp.json()["accepting_requests"] is True

    def test_non_manager_cannot_change_accepting_requests(self, client, db):
        """A regular member gets 403 if they try to change accepting_requests."""
        manager = _make_user(db, "manager_guard@example.com")
        league = _make_league(db, manager)

        member = _make_user(db, "member_guard@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        member_headers = _login_user(client, "member_guard@example.com")
        resp = client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=member_headers,
            json={"accepting_requests": False},
        )
        assert resp.status_code == 403

    def test_reopen_league_allows_new_joins(self, client, db):
        """After re-enabling, a new visitor can submit a join request."""
        manager = _make_user(db, "manager_cycle@example.com")
        league = _make_league(db, manager, accepting_requests=False)

        manager_headers = _login_user(client, "manager_cycle@example.com")
        # Re-enable.
        client.patch(
            f"/api/v1/leagues/{league.id}",
            headers=manager_headers,
            json={"accepting_requests": True},
        )

        visitor_headers = _register_and_login(client, "visitor_cycle@example.com")
        join_resp = client.post(
            f"/api/v1/leagues/join/{league.invite_code}",
            headers=visitor_headers,
        )
        assert join_resp.status_code == 201

    def test_accepting_requests_included_in_get_league_response(self, client, db):
        """GET /leagues/{id} returns the accepting_requests field."""
        manager = _make_user(db, "manager_get@example.com")
        league = _make_league(db, manager, accepting_requests=False)

        headers = _login_user(client, "manager_get@example.com")
        resp = client.get(f"/api/v1/leagues/{league.id}", headers=headers)
        assert resp.status_code == 200
        assert "accepting_requests" in resp.json()
        assert resp.json()["accepting_requests"] is False
