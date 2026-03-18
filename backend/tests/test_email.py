"""
Tests for app/services/email.py — transactional email service.

All SES API calls are mocked; no real AWS calls are made.
"""

import logging
from unittest.mock import MagicMock, patch

from app.services.email import send_password_reset_email, send_pick_reminder_email

# ---------------------------------------------------------------------------
# _ses_client() construction
# ---------------------------------------------------------------------------


class TestSesClientBuilding:
    """Verify that _ses_client() passes the right kwargs to boto3.client."""

    def test_uses_endpoint_url_when_set(self):
        """When AWS_ENDPOINT_URL is configured, boto3.client receives endpoint_url."""
        with patch("app.services.email.settings") as mock_settings:
            mock_settings.AWS_REGION = "us-east-1"
            mock_settings.AWS_ENDPOINT_URL = "http://localhost:4566"
            mock_settings.AWS_ACCESS_KEY_ID = ""
            mock_settings.AWS_SECRET_ACCESS_KEY = ""
            with patch("app.services.email.boto3") as mock_boto3:
                mock_boto3.client.return_value = MagicMock()
                # Import and call _ses_client after patching settings.
                from app.services.email import _ses_client

                _ses_client()
                call_kwargs = mock_boto3.client.call_args[1]
                assert call_kwargs.get("endpoint_url") == "http://localhost:4566"

    def test_uses_access_key_when_set(self):
        """When AWS_ACCESS_KEY_ID is set, boto3.client receives aws_access_key_id."""
        with patch("app.services.email.settings") as mock_settings:
            mock_settings.AWS_REGION = "us-east-1"
            mock_settings.AWS_ENDPOINT_URL = ""
            mock_settings.AWS_ACCESS_KEY_ID = "AKIATEST1234"
            mock_settings.AWS_SECRET_ACCESS_KEY = "secret"
            with patch("app.services.email.boto3") as mock_boto3:
                mock_boto3.client.return_value = MagicMock()
                from app.services.email import _ses_client

                _ses_client()
                call_kwargs = mock_boto3.client.call_args[1]
                assert call_kwargs.get("aws_access_key_id") == "AKIATEST1234"
                assert call_kwargs.get("aws_secret_access_key") == "secret"

    def test_minimal_client_no_endpoint(self):
        """When neither AWS_ENDPOINT_URL nor access keys are set, only region_name is passed."""
        with patch("app.services.email.settings") as mock_settings:
            mock_settings.AWS_REGION = "us-west-2"
            mock_settings.AWS_ENDPOINT_URL = ""
            mock_settings.AWS_ACCESS_KEY_ID = ""
            mock_settings.AWS_SECRET_ACCESS_KEY = ""
            with patch("app.services.email.boto3") as mock_boto3:
                mock_boto3.client.return_value = MagicMock()
                from app.services.email import _ses_client

                _ses_client()
                call_kwargs = mock_boto3.client.call_args[1]
                assert call_kwargs == {"region_name": "us-west-2"}
                assert "endpoint_url" not in call_kwargs
                assert "aws_access_key_id" not in call_kwargs


# ---------------------------------------------------------------------------
# send_password_reset_email
# ---------------------------------------------------------------------------


class TestSendPasswordResetEmail:
    """Tests for send_password_reset_email() — patch _ses_client for all cases."""

    def test_sends_email_to_correct_address(self):
        """send_email is called with the recipient in Destination ToAddresses."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            send_password_reset_email("user@example.com", "raw_token_abc")
            mock_client.send_email.assert_called_once()
            call_kwargs = mock_client.send_email.call_args[1]
            assert "user@example.com" in call_kwargs["Destination"]["ToAddresses"]

    def test_subject_contains_reset_password(self):
        """The email Subject line mentions 'Reset' so the recipient understands the intent."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            send_password_reset_email("user@example.com", "raw_token_abc")
            call_kwargs = mock_client.send_email.call_args[1]
            subject = call_kwargs["Message"]["Subject"]["Data"]
            assert "Reset" in subject or "reset" in subject

    def test_html_contains_token(self):
        """The HTML body contains the raw token embedded in the reset URL."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            send_password_reset_email("user@example.com", "tok_unique_xyz789")
            call_kwargs = mock_client.send_email.call_args[1]
            html_body = call_kwargs["Message"]["Body"]["Html"]["Data"]
            assert "tok_unique_xyz789" in html_body

    def test_url_logged_at_info_level(self, caplog):
        """The reset URL is logged at INFO level so local devs can copy it without email."""
        with patch("app.services.email._ses_client") as mock_ses:
            mock_ses.return_value = MagicMock()
            with caplog.at_level(logging.INFO, logger="app.services.email"):
                send_password_reset_email("user@example.com", "tok123")
            assert "tok123" in caplog.text

    def test_text_body_contains_reset_url(self):
        """The plain-text body includes the full reset URL for email clients that block HTML."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            with patch("app.services.email.settings") as mock_settings:
                mock_settings.FRONTEND_URL = "https://app.example.com"
                mock_settings.SES_FROM_EMAIL = "noreply@example.com"
                mock_settings.RESET_TOKEN_EXPIRE_HOURS = 1
                send_password_reset_email("user@example.com", "mytesttoken")
            call_kwargs = mock_client.send_email.call_args[1]
            text_body = call_kwargs["Message"]["Body"]["Text"]["Data"]
            assert "mytesttoken" in text_body
            assert "https://app.example.com" in text_body

    def test_ses_client_called_once_per_send(self):
        """A single send_password_reset_email call creates exactly one SES client and one send."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            send_password_reset_email("a@example.com", "sometoken")
            mock_ses_factory.assert_called_once()
            mock_client.send_email.assert_called_once()


# ---------------------------------------------------------------------------
# send_pick_reminder_email
# ---------------------------------------------------------------------------


class TestSendPickReminderEmail:
    """Tests for send_pick_reminder_email() — verifies CTA branching and content."""

    _LEAGUE_ID = "league-uuid-1234"
    _TOURNAMENT_NAME = "The Masters"

    def _call(self, pick_window_open: bool, **overrides):
        """Helper: invoke send_pick_reminder_email with sensible defaults."""
        defaults = dict(
            to_email="player@example.com",
            display_name="Alice",
            league_name="Sunday Hackers",
            league_id=self._LEAGUE_ID,
            tournament_name=self._TOURNAMENT_NAME,
            start_date="April 10",
            pick_window_open=pick_window_open,
        )
        defaults.update(overrides)
        send_pick_reminder_email(**defaults)

    def test_pick_window_open_html_contains_cta_button(self):
        """When pick_window_open=True the HTML body includes a link to the pick page."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            self._call(pick_window_open=True)
            call_kwargs = mock_client.send_email.call_args[1]
            html_body = call_kwargs["Message"]["Body"]["Html"]["Data"]
            expected_url = f"http://localhost:5173/leagues/{self._LEAGUE_ID}/pick"
            assert expected_url in html_body

    def test_pick_window_closed_html_contains_picks_not_open(self):
        """When pick_window_open=False the HTML body shows the 'Picks not open yet' notice."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            self._call(pick_window_open=False)
            call_kwargs = mock_client.send_email.call_args[1]
            html_body = call_kwargs["Message"]["Body"]["Html"]["Data"]
            assert "Picks not open yet" in html_body

    def test_subject_contains_tournament_name(self):
        """The subject line references the tournament so recipients know which event."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            self._call(pick_window_open=True)
            call_kwargs = mock_client.send_email.call_args[1]
            subject = call_kwargs["Message"]["Subject"]["Data"]
            assert self._TOURNAMENT_NAME in subject

    def test_destination_correct(self):
        """The email is addressed to the member's email, not a generic address."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            self._call(pick_window_open=True, to_email="specific@example.com")
            call_kwargs = mock_client.send_email.call_args[1]
            assert "specific@example.com" in call_kwargs["Destination"]["ToAddresses"]

    def test_text_body_contains_league_name(self):
        """The plain-text body includes the league name for context."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            self._call(pick_window_open=True, league_name="Super Golf League")
            call_kwargs = mock_client.send_email.call_args[1]
            text_body = call_kwargs["Message"]["Body"]["Text"]["Data"]
            assert "Super Golf League" in text_body

    def test_window_closed_text_has_no_cta_link(self):
        """When pick_window_open=False the plain-text body omits the pick URL."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            self._call(pick_window_open=False)
            call_kwargs = mock_client.send_email.call_args[1]
            text_body = call_kwargs["Message"]["Body"]["Text"]["Data"]
            pick_url = f"http://localhost:5173/leagues/{self._LEAGUE_ID}/pick"
            assert pick_url not in text_body

    def test_window_open_text_contains_pick_url(self):
        """When pick_window_open=True the plain-text body includes the pick URL."""
        with patch("app.services.email._ses_client") as mock_ses_factory:
            mock_client = MagicMock()
            mock_ses_factory.return_value = mock_client
            self._call(pick_window_open=True)
            call_kwargs = mock_client.send_email.call_args[1]
            text_body = call_kwargs["Message"]["Body"]["Text"]["Data"]
            pick_url = f"http://localhost:5173/leagues/{self._LEAGUE_ID}/pick"
            assert pick_url in text_body

    def test_reminder_email_logged_at_info_level(self, caplog):
        """send_pick_reminder_email logs the send attempt at INFO so local devs see it."""
        with patch("app.services.email._ses_client") as mock_ses:
            mock_ses.return_value = MagicMock()
            with caplog.at_level(logging.INFO, logger="app.services.email"):
                self._call(pick_window_open=True, to_email="log_check@example.com")
            assert "log_check@example.com" in caplog.text
