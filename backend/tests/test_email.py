"""
Tests for app/services/email.py — transactional email service.

All Resend API calls are mocked; no real emails are sent.
"""

import logging
from unittest.mock import patch

from app.services.email import send_password_reset_email, send_pick_reminder_email

# ---------------------------------------------------------------------------
# send_password_reset_email
# ---------------------------------------------------------------------------


class TestSendPasswordResetEmail:
    """Tests for send_password_reset_email() — patch resend.Emails.send."""

    def test_sends_email_to_correct_address(self):
        """resend.Emails.send is called with the recipient in 'to'."""
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                mock_settings.RESET_TOKEN_EXPIRE_HOURS = 1
                send_password_reset_email("user@example.com", "raw_token_abc")
            mock_resend.Emails.send.assert_called_once()
            call_args = mock_resend.Emails.send.call_args[0][0]
            assert "user@example.com" in call_args["to"]

    def test_subject_contains_reset_password(self):
        """The email subject mentions 'Reset'."""
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                mock_settings.RESET_TOKEN_EXPIRE_HOURS = 1
                send_password_reset_email("user@example.com", "raw_token_abc")
            call_args = mock_resend.Emails.send.call_args[0][0]
            assert "reset" in call_args["subject"].lower()

    def test_html_contains_token(self):
        """The HTML body contains the raw token embedded in the reset URL."""
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                mock_settings.RESET_TOKEN_EXPIRE_HOURS = 1
                send_password_reset_email("user@example.com", "tok_unique_xyz789")
            call_args = mock_resend.Emails.send.call_args[0][0]
            assert "tok_unique_xyz789" in call_args["html"]

    def test_url_logged_at_info_level(self, caplog):
        """The reset URL is logged at INFO level so local devs can copy it."""
        with patch("app.services.email.resend"):
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                mock_settings.RESET_TOKEN_EXPIRE_HOURS = 1
                with caplog.at_level(logging.INFO, logger="app.services.email"):
                    send_password_reset_email("user@example.com", "tok123")
            assert "tok123" in caplog.text

    def test_text_body_contains_reset_url(self):
        """The plain-text body includes the full reset URL."""
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "https://app.example.com"
                mock_settings.RESET_TOKEN_EXPIRE_HOURS = 1
                send_password_reset_email("user@example.com", "mytesttoken")
            call_args = mock_resend.Emails.send.call_args[0][0]
            assert "mytesttoken" in call_args["text"]
            assert "https://app.example.com" in call_args["text"]

    def test_no_api_key_skips_send(self):
        """When RESEND_API_KEY is empty, no email is sent (log only)."""
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = ""
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                mock_settings.RESET_TOKEN_EXPIRE_HOURS = 1
                send_password_reset_email("user@example.com", "tok_abc")
            mock_resend.Emails.send.assert_not_called()


# ---------------------------------------------------------------------------
# send_pick_reminder_email
# ---------------------------------------------------------------------------


class TestSendPickReminderEmail:
    """Tests for send_pick_reminder_email() — consolidated email with unpicked list."""

    _LEAGUE_ID = "league-uuid-1234"
    _TOURNAMENT_NAME = "The Masters"

    def _make_unpicked(self, pick_window_open: bool, **overrides):
        """Build a single unpicked entry dict."""
        defaults = dict(
            league_name="Sunday Hackers",
            league_id=self._LEAGUE_ID,
            tournament_name=self._TOURNAMENT_NAME,
            start_date="April 10",
            pick_window_open=pick_window_open,
        )
        defaults.update(overrides)
        return defaults

    def _call(self, unpicked_list, **overrides):
        """Invoke send_pick_reminder_email with sensible defaults."""
        defaults = dict(
            to_email="player@example.com",
            display_name="Alice",
            unpicked=unpicked_list,
        )
        defaults.update(overrides)
        send_pick_reminder_email(**defaults)

    def test_single_league_window_open_html_contains_cta(self):
        """Single unpicked entry with window open → CTA button in HTML."""
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                self._call([self._make_unpicked(pick_window_open=True)])
            call_args = mock_resend.Emails.send.call_args[0][0]
            expected_url = f"http://localhost:5173/leagues/{self._LEAGUE_ID}/pick"
            assert expected_url in call_args["html"]

    def test_single_league_window_closed_html_shows_not_open(self):
        """Single unpicked entry with window closed → 'Picks not open yet'."""
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                self._call([self._make_unpicked(pick_window_open=False)])
            call_args = mock_resend.Emails.send.call_args[0][0]
            assert "Picks not open yet" in call_args["html"]

    def test_subject_contains_tournament_name_single(self):
        """Single entry → subject mentions the tournament name."""
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                self._call([self._make_unpicked(pick_window_open=True)])
            call_args = mock_resend.Emails.send.call_args[0][0]
            assert self._TOURNAMENT_NAME in call_args["subject"]

    def test_multiple_entries_subject_shows_count(self):
        """Multiple entries → subject says 'N picks needed this week'."""
        entries = [
            self._make_unpicked(True, league_name="League A"),
            self._make_unpicked(True, league_name="League B"),
        ]
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                self._call(entries)
            call_args = mock_resend.Emails.send.call_args[0][0]
            assert "2 picks needed" in call_args["subject"]

    def test_multiple_entries_html_lists_all_leagues(self):
        """Multiple entries → HTML body lists all league names."""
        entries = [
            self._make_unpicked(True, league_name="Alpha League"),
            self._make_unpicked(True, league_name="Beta League"),
        ]
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                self._call(entries)
            call_args = mock_resend.Emails.send.call_args[0][0]
            assert "Alpha League" in call_args["html"]
            assert "Beta League" in call_args["html"]

    def test_destination_correct(self):
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                self._call(
                    [self._make_unpicked(True)],
                    to_email="specific@example.com",
                )
            call_args = mock_resend.Emails.send.call_args[0][0]
            assert "specific@example.com" in call_args["to"]

    def test_text_body_contains_league_name(self):
        with patch("app.services.email.resend") as mock_resend:
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                self._call(
                    [self._make_unpicked(True, league_name="Super Golf League")],
                )
            call_args = mock_resend.Emails.send.call_args[0][0]
            assert "Super Golf League" in call_args["text"]

    def test_reminder_email_logged_at_info_level(self, caplog):
        with patch("app.services.email.resend"):
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.RESEND_API_KEY = "re_test_key"
                mock_settings.EMAIL_FROM = "noreply@example.com"
                mock_settings.FRONTEND_URL = "http://localhost:5173"
                with caplog.at_level(logging.INFO, logger="app.services.email"):
                    self._call(
                        [self._make_unpicked(True)],
                        to_email="log_check@example.com",
                    )
            assert "log_check@example.com" in caplog.text
