"""
Tests for Google OAuth authentication.

Covers:
  - POST /auth/google  (not configured, invalid token, new user, existing user, account link)

verify_google_id_token is mocked so no real Google network calls are made.
"""

from unittest.mock import patch

import pytest
from google.auth.exceptions import GoogleAuthError

from app.models import User
from app.services.auth import hash_password

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GOOGLE_CLAIMS = {
    "sub": "google_sub_abc123",
    "email": "google@example.com",
    "name": "Google User",
}

_PATCH_TARGET = "app.routers.auth.verify_google_id_token"
_SETTINGS_PATCH = "app.routers.auth.settings"


def _post_google(client, id_token: str = "fake-id-token") -> object:
    return client.post("/api/v1/auth/google", json={"id_token": id_token})


# ---------------------------------------------------------------------------
# Google auth not configured
# ---------------------------------------------------------------------------


class TestGoogleAuthNotConfigured:
    def test_returns_501_when_no_client_id(self, client):
        """If GOOGLE_CLIENT_ID is empty/None, the endpoint returns 501."""
        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = ""
            resp = _post_google(client)
        assert resp.status_code == 501
        assert "not configured" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Invalid / malformed token
# ---------------------------------------------------------------------------


class TestGoogleAuthInvalidToken:
    def test_returns_401_on_google_auth_error(self, client):
        """A token rejected by Google causes a 401."""
        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "fake-client-id.apps.googleusercontent.com"
            with patch(_PATCH_TARGET, side_effect=GoogleAuthError("bad token")):
                resp = _post_google(client)
        assert resp.status_code == 401
        assert "invalid" in resp.json()["detail"].lower()

    def test_unexpected_error_propagates_instead_of_being_swallowed(self, client):
        """
        Non-Google errors (misconfiguration, library bugs) must NOT be caught
        as 401s — they should propagate so the operator sees them in logs/500s.

        TestClient re-raises server errors, so we verify the RuntimeError
        bubbles out rather than being silently swallowed.
        """
        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "fake-client-id.apps.googleusercontent.com"
            with patch(_PATCH_TARGET, side_effect=RuntimeError("unexpected")):
                with pytest.raises(RuntimeError, match="unexpected"):
                    _post_google(client)


# ---------------------------------------------------------------------------
# New user — first-time Google sign-in
# ---------------------------------------------------------------------------


class TestGoogleAuthNewUser:
    def test_creates_user_and_returns_access_token(self, client, db):
        """Brand-new Google user gets an account created and receives a token."""
        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "fake-client-id"
            with patch(_PATCH_TARGET, return_value=_GOOGLE_CLAIMS):
                resp = _post_google(client)

        assert resp.status_code == 200
        assert "access_token" in resp.json()

        user = db.query(User).filter_by(google_id="google_sub_abc123").first()
        assert user is not None
        assert user.email == "google@example.com"
        assert user.display_name == "Google User"
        assert user.password_hash is None  # Google accounts have no password

    def test_sets_refresh_cookie_for_new_user(self, client, db):
        """The refresh token cookie is set after first-time Google login."""
        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "fake-client-id"
            with patch(_PATCH_TARGET, return_value=_GOOGLE_CLAIMS):
                resp = _post_google(client)

        assert "refresh_token" in resp.cookies


# ---------------------------------------------------------------------------
# Existing Google user
# ---------------------------------------------------------------------------


class TestGoogleAuthExistingUser:
    def test_existing_google_user_logs_in_without_creating_duplicate(self, client, db):
        """A returning Google user is found by google_id and no new row is created."""
        # Pre-create the user as if they had logged in before.
        existing = User(
            email="google@example.com",
            google_id="google_sub_abc123",
            display_name="Existing Google User",
        )
        db.add(existing)
        db.commit()

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "fake-client-id"
            with patch(_PATCH_TARGET, return_value=_GOOGLE_CLAIMS):
                resp = _post_google(client)

        assert resp.status_code == 200
        # No duplicate user rows should exist.
        count = db.query(User).filter_by(google_id="google_sub_abc123").count()
        assert count == 1


# ---------------------------------------------------------------------------
# Account linking — email already registered with password
# ---------------------------------------------------------------------------


class TestGoogleAuthAccountLinking:
    def test_google_login_links_to_existing_email_account(self, client, db):
        """
        If a user registered with email/password and then signs in with Google
        (same email), the google_id is linked to the existing account.
        """
        # Existing email/password account.
        existing = User(
            email="google@example.com",
            password_hash=hash_password("password123"),
            display_name="Email User",
        )
        db.add(existing)
        db.commit()

        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "fake-client-id"
            with patch(_PATCH_TARGET, return_value=_GOOGLE_CLAIMS):
                resp = _post_google(client)

        assert resp.status_code == 200

        # The existing row should now have the google_id linked.
        db.refresh(existing)
        assert existing.google_id == "google_sub_abc123"

        # Still only one user row.
        count = db.query(User).filter_by(email="google@example.com").count()
        assert count == 1

    def test_linked_user_can_still_log_in_with_password(self, client, db):
        """After Google linking, the original email/password login still works."""
        existing = User(
            email="linked@example.com",
            password_hash=hash_password("password123"),
            display_name="Linked User",
        )
        db.add(existing)
        db.commit()

        claims = {**_GOOGLE_CLAIMS, "email": "linked@example.com", "sub": "sub_linked"}
        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "fake-client-id"
            with patch(_PATCH_TARGET, return_value=claims):
                _post_google(client)

        # Original password login should still work.
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": "linked@example.com", "password": "password123"},
        )
        assert login_resp.status_code == 200

    def test_email_normalized_to_lowercase_from_google_claims(self, client, db):
        """Google email is stored in lowercase even if claims contain mixed case."""
        claims = {**_GOOGLE_CLAIMS, "email": "CAPS@Example.COM", "sub": "sub_caps"}
        with patch(_SETTINGS_PATCH) as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "fake-client-id"
            with patch(_PATCH_TARGET, return_value=claims):
                resp = _post_google(client)

        assert resp.status_code == 200
        user = db.query(User).filter_by(google_id="sub_caps").first()
        assert user.email == "caps@example.com"
