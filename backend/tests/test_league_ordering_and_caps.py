"""
Tests for league ordering, per-user caps, and join request management.

Covers:
  - GET /users/me/leagues        Returns leagues in join-date order
  - GET /leagues/my-requests     Lists the user's own pending requests
  - DELETE /leagues/{id}/requests/me  Cancel own join request
  - League creation cap (5 leagues per user)
  - Join request cap enforcement
  - Leave league endpoint
  - Remove member endpoint (manager only)
  - Deny join request (manager only)
  - Approve join request (manager only)
"""

import uuid
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


def _make_league(db, creator: User, name: str = "Test League") -> League:
    league = League(name=name, created_by=creator.id)
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


def _register_and_login(client, email: str, display_name: str = "User") -> dict:
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "display_name": display_name},
    )
    return _login(client, email)


def _login(client, email: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# League ordering
# ---------------------------------------------------------------------------


class TestMyLeaguesOrdering:
    def test_leagues_returned_in_join_order(self, client, db):
        """
        GET /users/me/leagues returns leagues in the order the user joined them
        (ascending joined_at), not creation order or alphabetical.
        """
        # Manager creates three leagues.
        manager = _make_user(db, "manager_ord@example.com")
        league_a = _make_league(db, manager, "League A")
        league_b = _make_league(db, manager, "League B")
        league_c = _make_league(db, manager, "League C")

        # New user joins them in order: C → A → B (non-alphabetical).
        member = _make_user(db, "member_ord@example.com")
        for league in [league_c, league_a, league_b]:
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=member.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
            # Force a small time gap so joined_at ordering is deterministic.
            db.commit()

        member_headers = _login(client, "member_ord@example.com")
        resp = client.get("/api/v1/users/me/leagues", headers=member_headers)
        assert resp.status_code == 200
        names = [lg["name"] for lg in resp.json()]
        # Should appear in join order: C → A → B.
        assert names == ["League C", "League A", "League B"]

    def test_pending_leagues_excluded_from_my_leagues(self, client, db):
        """Leagues where the user is still pending are NOT returned."""
        manager = _make_user(db, "manager_excl@example.com")
        league = _make_league(db, manager, "Pending League")

        member = _make_user(db, "member_excl@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        db.commit()

        member_headers = _login(client, "member_excl@example.com")
        resp = client.get("/api/v1/users/me/leagues", headers=member_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 0


# ---------------------------------------------------------------------------
# my-requests
# ---------------------------------------------------------------------------


class TestMyRequests:
    def test_returns_pending_requests(self, client, db):
        manager = _make_user(db, "manager_myreq@example.com")
        league = _make_league(db, manager, "Pending League")

        requester = _make_user(db, "requester_myreq@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=requester.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        db.commit()

        requester_headers = _login(client, "requester_myreq@example.com")
        resp = client.get("/api/v1/leagues/my-requests", headers=requester_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["league_name"] == "Pending League"

    def test_returns_empty_when_no_pending_requests(self, client, db):
        headers = _register_and_login(client, "no_req@example.com")
        resp = client.get("/api/v1/leagues/my-requests", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_approved_memberships_not_in_my_requests(self, client, db):
        manager = _make_user(db, "manager_approved@example.com")
        league = _make_league(db, manager)

        member = _make_user(db, "member_approved@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        member_headers = _login(client, "member_approved@example.com")
        resp = client.get("/api/v1/leagues/my-requests", headers=member_headers)
        assert resp.status_code == 200
        # Approved memberships don't appear in my-requests.
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Cancel my join request
# ---------------------------------------------------------------------------


class TestCancelMyRequest:
    def test_user_can_cancel_own_pending_request(self, client, db):
        manager = _make_user(db, "manager_cancel@example.com")
        league = _make_league(db, manager)

        requester = _make_user(db, "requester_cancel@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=requester.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        db.commit()

        requester_headers = _login(client, "requester_cancel@example.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/requests/me",
            headers=requester_headers,
        )
        assert resp.status_code == 204

        # Verify the row is gone.
        remaining = (
            db.query(LeagueMember).filter_by(league_id=league.id, user_id=requester.id).first()
        )
        assert remaining is None

    def test_cancel_nonexistent_request_returns_404(self, client, db):
        manager = _make_user(db, "manager_nocancel@example.com")
        league = _make_league(db, manager)

        visitor_headers = _register_and_login(client, "visitor_nocancel@example.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/requests/me",
            headers=visitor_headers,
        )
        assert resp.status_code == 404

    def test_approved_member_cannot_cancel_via_request_endpoint(self, client, db):
        """The cancel endpoint only works on PENDING records, not APPROVED memberships."""
        manager = _make_user(db, "manager_nocancel2@example.com")
        league = _make_league(db, manager)

        member = _make_user(db, "member_nocancel@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        member_headers = _login(client, "member_nocancel@example.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/requests/me",
            headers=member_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Leave league
# ---------------------------------------------------------------------------


class TestLeaveLeague:
    def test_member_can_leave_league(self, client, db):
        manager = _make_user(db, "manager_leave@example.com")
        league = _make_league(db, manager)

        member = _make_user(db, "member_leave@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        member_headers = _login(client, "member_leave@example.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/members/me",
            headers=member_headers,
        )
        assert resp.status_code == 204

        remaining = db.query(LeagueMember).filter_by(league_id=league.id, user_id=member.id).first()
        assert remaining is None

    def test_manager_can_leave_own_league(self, client, db):
        manager = _make_user(db, "manager_self_leave@example.com")
        league = _make_league(db, manager)

        manager_headers = _login(client, "manager_self_leave@example.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/members/me",
            headers=manager_headers,
        )
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Remove member (manager)
# ---------------------------------------------------------------------------


class TestRemoveMember:
    def test_manager_can_remove_member(self, client, db):
        manager = _make_user(db, "manager_rm@example.com")
        league = _make_league(db, manager)

        member = _make_user(db, "member_rm@example.com")
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        manager_headers = _login(client, "manager_rm@example.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/members/{member.id}",
            headers=manager_headers,
        )
        assert resp.status_code == 204

        remaining = db.query(LeagueMember).filter_by(league_id=league.id, user_id=member.id).first()
        assert remaining is None

    def test_manager_cannot_remove_themselves(self, client, db):
        manager = _make_user(db, "manager_selfremove@example.com")
        league = _make_league(db, manager)

        manager_headers = _login(client, "manager_selfremove@example.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/members/{manager.id}",
            headers=manager_headers,
        )
        assert resp.status_code == 400
        assert "cannot remove yourself" in resp.json()["detail"].lower()

    def test_remove_nonexistent_member_returns_404(self, client, db):
        manager = _make_user(db, "manager_nofind@example.com")
        league = _make_league(db, manager)

        manager_headers = _login(client, "manager_nofind@example.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/members/{uuid.uuid4()}",
            headers=manager_headers,
        )
        assert resp.status_code == 404

    def test_non_manager_cannot_remove_members(self, client, db):
        manager = _make_user(db, "manager_perm@example.com")
        league = _make_league(db, manager)

        member_a = _make_user(db, "member_a_perm@example.com")
        member_b = _make_user(db, "member_b_perm@example.com")
        for user in [member_a, member_b]:
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=user.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=LeagueMemberStatus.APPROVED.value,
                )
            )
        db.commit()

        member_a_headers = _login(client, "member_a_perm@example.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/members/{member_b.id}",
            headers=member_a_headers,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Approve / Deny join requests
# ---------------------------------------------------------------------------


class TestApproveAndDenyRequests:
    def _setup_pending_request(self, db, manager_email: str, requester_email: str):
        manager = _make_user(db, manager_email)
        league = _make_league(db, manager)
        requester = _make_user(db, requester_email)
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=requester.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.PENDING.value,
            )
        )
        db.commit()
        return league, requester

    def test_manager_can_approve_pending_request(self, client, db):
        league, requester = self._setup_pending_request(
            db, "manager_approve@example.com", "requester_approve@example.com"
        )
        headers = _login(client, "manager_approve@example.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/requests/{requester.id}/approve",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

        member = db.query(LeagueMember).filter_by(league_id=league.id, user_id=requester.id).first()
        assert member.status == "approved"

    def test_manager_can_deny_pending_request(self, client, db):
        league, requester = self._setup_pending_request(
            db, "manager_deny@example.com", "requester_deny@example.com"
        )
        headers = _login(client, "manager_deny@example.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/requests/{requester.id}",
            headers=headers,
        )
        assert resp.status_code == 204

        # Row should be deleted after denial.
        member = db.query(LeagueMember).filter_by(league_id=league.id, user_id=requester.id).first()
        assert member is None

    def test_approve_nonexistent_request_returns_404(self, client, db):
        manager = _make_user(db, "manager_noapp@example.com")
        league = _make_league(db, manager)

        headers = _login(client, "manager_noapp@example.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/requests/{uuid.uuid4()}/approve",
            headers=headers,
        )
        assert resp.status_code == 404

    def test_deny_nonexistent_request_returns_404(self, client, db):
        manager = _make_user(db, "manager_nodeny@example.com")
        league = _make_league(db, manager)

        headers = _login(client, "manager_nodeny@example.com")
        resp = client.delete(
            f"/api/v1/leagues/{league.id}/requests/{uuid.uuid4()}",
            headers=headers,
        )
        assert resp.status_code == 404

    def test_non_manager_cannot_approve_requests(self, client, db):
        manager = _make_user(db, "manager_perm2@example.com")
        league = _make_league(db, manager)
        requester = _make_user(db, "requester_perm2@example.com")
        member = _make_user(db, "member_perm2@example.com")
        for user, role, status in [
            (requester, LeagueMemberRole.MEMBER.value, LeagueMemberStatus.PENDING.value),
            (member, LeagueMemberRole.MEMBER.value, LeagueMemberStatus.APPROVED.value),
        ]:
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=user.id,
                    role=role,
                    status=status,
                )
            )
        db.commit()

        member_headers = _login(client, "member_perm2@example.com")
        resp = client.post(
            f"/api/v1/leagues/{league.id}/requests/{requester.id}/approve",
            headers=member_headers,
        )
        assert resp.status_code == 403

    def test_list_pending_requests_shows_only_pending(self, client, db):
        manager = _make_user(db, "manager_list@example.com")
        league = _make_league(db, manager)

        pending_user = _make_user(db, "pending_list@example.com")
        approved_user = _make_user(db, "approved_list@example.com")
        for user, status in [
            (pending_user, LeagueMemberStatus.PENDING.value),
            (approved_user, LeagueMemberStatus.APPROVED.value),
        ]:
            db.add(
                LeagueMember(
                    league_id=league.id,
                    user_id=user.id,
                    role=LeagueMemberRole.MEMBER.value,
                    status=status,
                )
            )
        db.commit()

        headers = _login(client, "manager_list@example.com")
        resp = client.get(f"/api/v1/leagues/{league.id}/requests", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        # Only the pending user should appear.
        assert len(data) == 1
        emails = [r["user"]["email"] for r in data]
        assert "pending_list@example.com" in emails
        assert "approved_list@example.com" not in emails


# ---------------------------------------------------------------------------
# League creation cap
# ---------------------------------------------------------------------------


class TestLeagueCreationCap:
    def test_user_can_create_up_to_cap(self, client, db):
        """A user can create/join up to USER_LEAGUE_CAP (5) leagues."""
        _make_user(db, "manager_cap@example.com")
        headers = _login(client, "manager_cap@example.com")

        # First 4 leagues via API (already a member as manager = 1 per creation)
        for i in range(4):
            resp = client.post(
                "/api/v1/leagues",
                headers=headers,
                json={"name": f"League {i}"},
            )
            assert resp.status_code == 201

        # 5th league — still within the cap.
        resp5 = client.post(
            "/api/v1/leagues",
            headers=headers,
            json={"name": "League 4"},
        )
        assert resp5.status_code == 201

    def test_creation_fails_at_cap_limit(self, client, db):
        """Creating a 6th league should fail with 400."""
        _make_user(db, "manager_overcap@example.com")
        headers = _login(client, "manager_overcap@example.com")

        for i in range(5):
            client.post("/api/v1/leagues", headers=headers, json={"name": f"League {i}"})

        # 6th attempt — should be rejected.
        resp6 = client.post(
            "/api/v1/leagues",
            headers=headers,
            json={"name": "League 5"},
        )
        assert resp6.status_code == 400
        assert "maximum" in resp6.json()["detail"].lower()
