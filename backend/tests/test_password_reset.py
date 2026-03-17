"""
Tests for the password reset flow.

Covers:
  - POST /auth/forgot-password  (always 200, no email enumeration)
  - POST /auth/reset-password   (valid token → auto-login, invalid → 400)

Email sending is mocked so tests never hit AWS SES.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.models import User
from app.models.password_reset_token import PasswordResetToken
from app.services.auth import generate_reset_token

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register(client, email="reset@example.com", password="password123"):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": "Reset User"},
    )
    assert resp.status_code == 201
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# forgot-password
# ---------------------------------------------------------------------------


class TestForgotPassword:
    def test_known_email_returns_200(self, client):
        """Endpoint always returns 200 regardless of whether email is registered."""
        _register(client, "known@example.com")
        with patch("app.routers.auth.send_password_reset_email") as mock_send:
            resp = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "known@example.com"},
            )
        assert resp.status_code == 200
        assert "detail" in resp.json()
        mock_send.assert_called_once()

    def test_unknown_email_also_returns_200(self, client):
        """Returns 200 for unknown email to prevent account enumeration."""
        with patch("app.routers.auth.send_password_reset_email") as mock_send:
            resp = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "nobody@example.com"},
            )
        assert resp.status_code == 200
        mock_send.assert_not_called()

    def test_google_only_account_silently_skipped(self, client, db):
        """Google-only accounts (no password_hash) cannot reset a password."""
        user = User(
            email="google@example.com",
            google_id="google_sub_12345",
            display_name="Google User",
            password_hash=None,  # no password
        )
        db.add(user)
        db.commit()

        with patch("app.routers.auth.send_password_reset_email") as mock_send:
            resp = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "google@example.com"},
            )
        assert resp.status_code == 200
        mock_send.assert_not_called()

    def test_generates_reset_token_in_db(self, client, db):
        """A valid forgot-password request stores a hashed token in the DB."""
        _register(client, "token@example.com")
        with patch("app.routers.auth.send_password_reset_email"):
            client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "token@example.com"},
            )

        token_count = db.query(PasswordResetToken).count()
        assert token_count == 1

    def test_replaces_existing_token_with_new_one(self, client, db):
        """A second forgot-password request invalidates the first token."""
        _register(client, "replace@example.com")
        with patch("app.routers.auth.send_password_reset_email"):
            client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "replace@example.com"},
            )
        first_token = db.query(PasswordResetToken).first()
        first_hash = first_token.token_hash

        with patch("app.routers.auth.send_password_reset_email"):
            client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "replace@example.com"},
            )

        tokens = db.query(PasswordResetToken).all()
        # Only one token should exist — the new one replaced the old one.
        assert len(tokens) == 1
        assert tokens[0].token_hash != first_hash

    def test_email_send_failure_still_returns_200(self, client):
        """SES failure should not expose whether the account exists."""
        _register(client, "fail@example.com")
        with patch(
            "app.routers.auth.send_password_reset_email",
            side_effect=Exception("SES error"),
        ):
            resp = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": "fail@example.com"},
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# reset-password
# ---------------------------------------------------------------------------


class TestResetPassword:
    def _get_raw_token(self, client, db, email="reset@example.com") -> str:
        """Register a user, trigger forgot-password, return the raw token from DB."""
        _register(client, email)
        user = db.query(User).filter_by(email=email).first()
        return generate_reset_token(db, user)

    def test_valid_token_resets_password_and_returns_access_token(self, client, db):
        """Happy path: valid token → password updated, user auto-logged-in."""
        raw = self._get_raw_token(client, db)

        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "new_password": "newpassword456"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_can_login_with_new_password_after_reset(self, client, db):
        """After reset, the new password works for login; old password does not."""
        email = "login_after@example.com"
        raw = self._get_raw_token(client, db, email)

        client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "new_password": "brandnewpassword"},
        )

        # Old password should be rejected.
        old_login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "password123"},
        )
        assert old_login.status_code == 401

        # New password should work.
        new_login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "brandnewpassword"},
        )
        assert new_login.status_code == 200

    def test_invalid_token_returns_400(self, client):
        """A random/non-existent token returns 400 (not 401 or 404)."""
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "completelyfaketoken", "new_password": "newpass123"},
        )
        assert resp.status_code == 400

    def test_token_is_single_use(self, client, db):
        """A consumed token cannot be used a second time."""
        raw = self._get_raw_token(client, db)

        # First use — succeeds.
        resp1 = client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "new_password": "firstnewpass"},
        )
        assert resp1.status_code == 200

        # Second use of the same token — must fail.
        resp2 = client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "new_password": "secondnewpass"},
        )
        assert resp2.status_code == 400

    def test_expired_token_returns_400(self, client, db):
        """A token past its 1-hour TTL is rejected."""
        raw = self._get_raw_token(client, db, "expired@example.com")

        # Manually expire the token by backfilling expires_at.
        record = db.query(PasswordResetToken).first()
        record.expires_at = datetime.now(tz=UTC) - timedelta(hours=2)
        db.commit()

        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "new_password": "anypassword"},
        )
        assert resp.status_code == 400

    def test_reset_issues_refresh_cookie(self, client, db):
        """A successful reset sets the httpOnly refresh_token cookie."""
        raw = self._get_raw_token(client, db, "cookie@example.com")

        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw, "new_password": "newpass123"},
        )
        assert resp.status_code == 200
        assert "refresh_token" in resp.cookies
