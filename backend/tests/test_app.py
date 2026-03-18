"""
Tests for app-level endpoints and cross-cutting behavior.

Covers:
  GET /health              — Kubernetes liveness probe
  GET /api/v1/config       — public feature flags (LEAGUE_CREATION_RESTRICTED)
  Token edge cases         — deleted user, wrong token type, malformed
  Pending member message   — require_league_member gives descriptive 403
  Refresh token edge cases — get_refresh_token_user error paths
"""

import uuid

from app.models import League, LeagueMember, LeagueMemberRole, LeagueMemberStatus, Season, User
from app.services.auth import create_access_token, create_refresh_token, hash_password

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


def _auth_headers(client, email: str) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert resp.status_code == 200, resp.json()
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_league_with_member(db, creator: User) -> League:
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
    db.add(Season(league_id=league.id, year=2026, is_active=True))
    db.commit()
    db.refresh(league)
    return league


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_returns_ok_status(self, client):
        resp = client.get("/health")
        assert resp.json() == {"status": "ok"}

    def test_no_auth_required(self, client):
        """Kubernetes probes hit /health without credentials; must never return 401."""
        resp = client.get("/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/config
# ---------------------------------------------------------------------------


class TestPublicConfig:
    def test_returns_200_without_auth(self, client):
        resp = client.get("/api/v1/config")
        assert resp.status_code == 200

    def test_contains_league_creation_restricted_field(self, client):
        resp = client.get("/api/v1/config")
        assert "league_creation_restricted" in resp.json()

    def test_returns_false_by_default(self, client):
        """conftest.py sets LEAGUE_CREATION_RESTRICTED=false to keep test isolation."""
        resp = client.get("/api/v1/config")
        assert resp.json()["league_creation_restricted"] is False

    def test_reflects_true_when_flag_toggled(self, client):
        """The endpoint reads directly from settings so toggling the setting changes the
        response."""
        from app.config import settings

        original = settings.LEAGUE_CREATION_RESTRICTED
        try:
            settings.LEAGUE_CREATION_RESTRICTED = True
            resp = client.get("/api/v1/config")
            assert resp.json()["league_creation_restricted"] is True
        finally:
            settings.LEAGUE_CREATION_RESTRICTED = original


# ---------------------------------------------------------------------------
# Token edge cases (get_current_user dependency)
# ---------------------------------------------------------------------------


class TestAccessTokenEdgeCases:
    def test_missing_token_returns_401(self, client):
        resp = client.get("/api/v1/users/me")
        assert resp.status_code == 401

    def test_malformed_token_returns_401(self, client):
        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
        )
        assert resp.status_code == 401

    def test_bearer_prefix_missing_returns_401(self, client):
        """Authorization header without 'Bearer ' prefix is rejected."""
        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "sometoken"},
        )
        assert resp.status_code == 401

    def test_valid_token_for_deleted_user_returns_401(self, client, db):
        """
        Token passes signature verification but the referenced user no longer
        exists in the database.  This ensures a deleted account cannot
        re-authenticate with an old token.
        """
        phantom_id = str(uuid.uuid4())
        token = create_access_token(phantom_id)
        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        assert "not found" in resp.json()["detail"].lower()

    def test_refresh_token_rejected_as_access_token(self, client, db):
        """
        A refresh token must not grant access to endpoints that expect an
        access token — the 'type' claim in the JWT must be checked.
        """
        user = _make_user(db, "wrongtype@example.com")
        refresh = create_refresh_token(str(user.id))
        resp = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {refresh}"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Refresh token edge cases (get_refresh_token_user dependency)
# ---------------------------------------------------------------------------


class TestRefreshTokenEdgeCases:
    def test_no_cookie_returns_401(self, client):
        """POST /auth/refresh without a cookie must return 401, not 500."""
        client.cookies.delete("refresh_token")
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 401
        assert "refresh" in resp.json()["detail"].lower()

    def test_malformed_cookie_returns_401(self, client):
        client.cookies["refresh_token"] = "not.a.valid.jwt"
        resp = client.post("/api/v1/auth/refresh")
        client.cookies.delete("refresh_token")
        assert resp.status_code == 401

    def test_access_token_in_refresh_cookie_returns_401(self, client, db):
        """
        Using an access token (type=access) as the refresh cookie must be
        rejected — the endpoint only accepts tokens with type=refresh.
        """
        user = _make_user(db, "wrongcookietype@example.com")
        access = create_access_token(str(user.id))
        client.cookies["refresh_token"] = access
        resp = client.post("/api/v1/auth/refresh")
        client.cookies.delete("refresh_token")
        assert resp.status_code == 401

    def test_valid_refresh_cookie_returns_new_access_token(self, client, db):
        """Confirm that a valid refresh cookie works — regression guard."""
        _make_user(db, "validrefresh@example.com")
        # Log in to get the httpOnly refresh cookie set on the client
        client.post(
            "/api/v1/auth/login",
            json={"email": "validrefresh@example.com", "password": "password123"},
        )
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 200
        assert "access_token" in resp.json()


# ---------------------------------------------------------------------------
# require_league_member error messages (dependency error paths)
# ---------------------------------------------------------------------------


class TestLeagueMembershipErrors:
    def test_pending_member_gets_descriptive_403(self, client, db):
        """
        A user with a pending join request should see a message explaining
        their request is awaiting approval, not a generic 'not a member' error.
        """
        manager = _make_user(db, "manager@example.com")
        requester = _make_user(db, "requester@example.com")
        league = _make_league_with_member(db, manager)

        # Requester has submitted a join request but not yet been approved
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=requester.id,
                role=LeagueMemberRole.MEMBER.value,
                status="pending",
            )
        )
        db.commit()

        headers = _auth_headers(client, "requester@example.com")
        resp = client.get(f"/api/v1/leagues/{league.id}/standings", headers=headers)

        assert resp.status_code == 403
        assert "pending" in resp.json()["detail"].lower()

    def test_non_member_gets_generic_403(self, client, db):
        manager = _make_user(db, "manager2@example.com")
        _make_user(db, "outsider@example.com")
        league = _make_league_with_member(db, manager)

        headers = _auth_headers(client, "outsider@example.com")
        resp = client.get(f"/api/v1/leagues/{league.id}/standings", headers=headers)

        assert resp.status_code == 403
        assert "not a member" in resp.json()["detail"].lower()

    def test_member_requires_manager_role_for_manager_endpoints(self, client, db):
        """A plain member cannot call manager-only endpoints like PUT tournaments."""
        manager = _make_user(db, "manager3@example.com")
        member = _make_user(db, "member3@example.com")
        league = _make_league_with_member(db, manager)
        db.add(
            LeagueMember(
                league_id=league.id,
                user_id=member.id,
                role=LeagueMemberRole.MEMBER.value,
                status=LeagueMemberStatus.APPROVED.value,
            )
        )
        db.commit()

        headers = _auth_headers(client, "member3@example.com")
        resp = client.put(
            f"/api/v1/leagues/{league.id}/tournaments",
            json={"tournaments": []},
            headers=headers,
        )
        assert resp.status_code == 403
        assert "manager" in resp.json()["detail"].lower()
