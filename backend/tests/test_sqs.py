"""
Tests for app/services/sqs.py — SQS client wrapper.

All boto3 calls are mocked. No real AWS or LocalStack calls are made.

Note on import patching: _get_client() does `import boto3` inside the function
body, so the correct patch target is `boto3.client` (the global boto3 module
already imported by the time tests run), not `app.services.sqs.boto3`.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.services.sqs import _get_client, consume, get_queue_url, publish

# ---------------------------------------------------------------------------
# _get_client()
# ---------------------------------------------------------------------------


class TestGetClient:
    """_get_client() builds a boto3 SQS client from environment variables."""

    def test_includes_region_from_env(self):
        """region_name is sourced from AWS_REGION — required in both local and prod."""
        with patch.dict(os.environ, {"AWS_REGION": "us-east-2"}, clear=False):
            with patch("boto3.client") as mock_client:
                mock_client.return_value = MagicMock()
                _get_client()
                call_kwargs = mock_client.call_args[1]
                assert call_kwargs["region_name"] == "us-east-2"

    def test_includes_endpoint_when_set(self):
        """When AWS_ENDPOINT_URL is present, endpoint_url is forwarded to boto3.client."""
        env = {"AWS_REGION": "us-east-2", "AWS_ENDPOINT_URL": "http://localhost:4566"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_client:
                mock_client.return_value = MagicMock()
                _get_client()
                call_kwargs = mock_client.call_args[1]
                assert call_kwargs.get("endpoint_url") == "http://localhost:4566"

    def test_no_endpoint_when_not_set(self):
        """When AWS_ENDPOINT_URL is absent (production), endpoint_url must not appear."""
        env = {"AWS_REGION": "us-east-2"}
        # Ensure the variable is absent even if the outer environment has it.
        clean_env = {k: v for k, v in os.environ.items() if k != "AWS_ENDPOINT_URL"}
        clean_env.update(env)
        with patch.dict(os.environ, clean_env, clear=True):
            with patch("boto3.client") as mock_client:
                mock_client.return_value = MagicMock()
                _get_client()
                call_kwargs = mock_client.call_args[1]
                assert "endpoint_url" not in call_kwargs

    def test_missing_aws_region_raises_key_error(self):
        """If AWS_REGION is not set at all, _get_client() must propagate a KeyError."""
        clean_env = {k: v for k, v in os.environ.items() if k != "AWS_REGION"}
        with patch.dict(os.environ, clean_env, clear=True):
            with patch("boto3.client"):
                with pytest.raises(KeyError):
                    _get_client()

    def test_boto3_called_with_sqs_service(self):
        """The first positional argument to boto3.client must be 'sqs'."""
        with patch.dict(os.environ, {"AWS_REGION": "us-east-2"}, clear=False):
            with patch("boto3.client") as mock_client:
                mock_client.return_value = MagicMock()
                _get_client()
                # First positional arg is the service name.
                assert mock_client.call_args[0][0] == "sqs"


# ---------------------------------------------------------------------------
# get_queue_url()
# ---------------------------------------------------------------------------


class TestGetQueueUrl:
    """get_queue_url() reads SQS_QUEUE_URL from the environment."""

    def test_returns_sqs_queue_url(self):
        """Returns the URL string set in SQS_QUEUE_URL."""
        env = {"SQS_QUEUE_URL": "https://sqs.us-east-2.amazonaws.com/123456/my-queue"}
        with patch.dict(os.environ, env, clear=False):
            url = get_queue_url()
            assert url == "https://sqs.us-east-2.amazonaws.com/123456/my-queue"

    def test_missing_raises_key_error(self):
        """If SQS_QUEUE_URL is unset, a KeyError is raised immediately."""
        clean_env = {k: v for k, v in os.environ.items() if k != "SQS_QUEUE_URL"}
        with patch.dict(os.environ, clean_env, clear=True):
            with pytest.raises(KeyError):
                get_queue_url()


# ---------------------------------------------------------------------------
# publish()
# ---------------------------------------------------------------------------


class TestPublish:
    """publish() serialises the event and sends it to SQS via send_message."""

    def test_sends_message_with_correct_body(self):
        """The MessageBody JSON contains type and all extra payload kwargs."""
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/queue"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                publish("TOURNAMENT_COMPLETED", tournament_id="abc123")
                mock_sqs.send_message.assert_called_once()
                call_kwargs = mock_sqs.send_message.call_args[1]
                body = json.loads(call_kwargs["MessageBody"])
                assert body["type"] == "TOURNAMENT_COMPLETED"
                assert body["tournament_id"] == "abc123"

    def test_uses_queue_url_from_env(self):
        """send_message receives the QueueUrl from the SQS_QUEUE_URL environment variable."""
        queue_url = "https://sqs.us-east-2.amazonaws.com/999/test-queue"
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": queue_url}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                publish("SOME_EVENT")
                call_kwargs = mock_sqs.send_message.call_args[1]
                assert call_kwargs["QueueUrl"] == queue_url

    def test_multiple_payload_fields_included(self):
        """All keyword arguments become top-level keys in the serialised message."""
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                publish("TOURNAMENT_IN_PROGRESS", tournament_id="t1", league_id="l1")
                call_kwargs = mock_sqs.send_message.call_args[1]
                body = json.loads(call_kwargs["MessageBody"])
                assert body["tournament_id"] == "t1"
                assert body["league_id"] == "l1"

    def test_message_body_is_valid_json(self):
        """The serialised message body must be valid JSON (not a repr or something else)."""
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                publish("ANY_EVENT", foo="bar")
                call_kwargs = mock_sqs.send_message.call_args[1]
                # Should not raise.
                parsed = json.loads(call_kwargs["MessageBody"])
                assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# consume()
# ---------------------------------------------------------------------------


class TestConsume:
    """
    consume() loops forever polling SQS. Tests inject an exception on the second
    receive_message call to break the loop and then assert on what happened.
    """

    def test_processes_messages_and_deletes_on_success(self):
        """A successfully handled message is deleted from the queue."""
        handler = MagicMock()
        msg = {"Body": json.dumps({"type": "TEST"}), "ReceiptHandle": "receipt_123"}
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                # First poll returns one message; second poll raises to exit the loop.
                mock_sqs.receive_message.side_effect = [
                    {"Messages": [msg]},
                    Exception("stop"),
                ]
                with pytest.raises(Exception, match="stop"):
                    consume(handler)
                handler.assert_called_once_with({"type": "TEST"})
                mock_sqs.delete_message.assert_called_once_with(
                    QueueUrl="https://sqs.test/q", ReceiptHandle="receipt_123"
                )

    def test_does_not_delete_message_on_handler_exception(self):
        """If the handler raises, the message is NOT deleted so SQS can retry it."""
        handler = MagicMock(side_effect=RuntimeError("handler failed"))
        msg = {"Body": json.dumps({"type": "TEST"}), "ReceiptHandle": "receipt_456"}
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                mock_sqs.receive_message.side_effect = [
                    {"Messages": [msg]},
                    Exception("stop"),
                ]
                with pytest.raises(Exception, match="stop"):
                    consume(handler)
                mock_sqs.delete_message.assert_not_called()

    def test_handles_empty_message_batch(self):
        """An empty Messages list results in zero handler calls and zero deletes."""
        handler = MagicMock()
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                mock_sqs.receive_message.side_effect = [{"Messages": []}, Exception("stop")]
                with pytest.raises(Exception, match="stop"):
                    consume(handler)
                handler.assert_not_called()
                mock_sqs.delete_message.assert_not_called()

    def test_processes_multiple_messages_in_one_batch(self):
        """All messages in a single receive_message response are processed."""
        handler = MagicMock()
        msgs = [
            {"Body": json.dumps({"type": "A"}), "ReceiptHandle": "r1"},
            {"Body": json.dumps({"type": "B"}), "ReceiptHandle": "r2"},
            {"Body": json.dumps({"type": "C"}), "ReceiptHandle": "r3"},
        ]
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                mock_sqs.receive_message.side_effect = [
                    {"Messages": msgs},
                    Exception("stop"),
                ]
                with pytest.raises(Exception, match="stop"):
                    consume(handler)
                assert handler.call_count == 3
                assert mock_sqs.delete_message.call_count == 3

    def test_partial_batch_failure_deletes_only_successful_messages(self):
        """If the second message in a batch fails, only the first is deleted."""
        call_count = 0

        def flaky_handler(body):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("second fails")

        msgs = [
            {"Body": json.dumps({"type": "OK"}), "ReceiptHandle": "r_ok"},
            {"Body": json.dumps({"type": "FAIL"}), "ReceiptHandle": "r_fail"},
        ]
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                mock_sqs.receive_message.side_effect = [
                    {"Messages": msgs},
                    Exception("stop"),
                ]
                with pytest.raises(Exception, match="stop"):
                    consume(flaky_handler)
                # Only the first message (success) should be deleted.
                mock_sqs.delete_message.assert_called_once_with(
                    QueueUrl="https://sqs.test/q", ReceiptHandle="r_ok"
                )

    def test_missing_messages_key_handled_gracefully(self):
        """A response with no 'Messages' key (SQS timeout) should iterate zero messages."""
        handler = MagicMock()
        env = {"AWS_REGION": "us-east-2", "SQS_QUEUE_URL": "https://sqs.test/q"}
        with patch.dict(os.environ, env, clear=False):
            with patch("boto3.client") as mock_boto3_client:
                mock_sqs = MagicMock()
                mock_boto3_client.return_value = mock_sqs
                # No 'Messages' key — simulates a long-polling timeout with 0 messages.
                mock_sqs.receive_message.side_effect = [{}, Exception("stop")]
                with pytest.raises(Exception, match="stop"):
                    consume(handler)
                handler.assert_not_called()
