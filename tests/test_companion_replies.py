"""Tests for reply helpers — build_reply_envelope."""
from __future__ import annotations

from aura.companion.replies import build_reply_envelope


class TestBuildReplyEnvelope:
    """Envelope construction logic."""

    def test_preserves_sender_device_id_routing(self) -> None:
        msg = {
            "id": "msg_123",
            "sender_device_id": "phone_abc",
            "type": "test.request",
            "payload": {},
        }
        envelope = build_reply_envelope(msg, "test.response", {"ok": True})

        assert envelope is not None
        assert envelope["desktop_id"] == "phone_abc"
        assert envelope["in_response_to"] == "msg_123"

    def test_returns_none_when_sender_device_id_missing(self) -> None:
        msg = {"id": "msg_123", "type": "test.request", "payload": {}}
        envelope = build_reply_envelope(msg, "test.response", {"ok": True})

        assert envelope is None

    def test_envelope_structure_contains_expected_fields(self) -> None:
        msg = {
            "id": "req_42",
            "sender_device_id": "phone_xyz",
            "type": "conversation.list",
            "payload": {},
        }
        envelope = build_reply_envelope(
            msg,
            "conversation.list_result",
            {"threads": []},
            project_id="proj_1",
            conversation_id="conv_2",
        )

        assert envelope is not None
        assert envelope["type"] == "conversation.list_result"
        assert envelope["project_id"] == "proj_1"
        assert envelope["conversation_id"] == "conv_2"
        assert envelope["in_response_to"] == "req_42"
        assert envelope["desktop_id"] == "phone_xyz"
        assert "payload" in envelope
        assert envelope["payload"] == {"threads": []}

    def test_optional_ids_default_to_empty_string(self) -> None:
        msg = {"id": "req_1", "sender_device_id": "phone_1", "type": "x", "payload": {}}
        envelope = build_reply_envelope(msg, "x_result", {})

        assert envelope is not None
        assert envelope["project_id"] == ""
        assert envelope["conversation_id"] == ""
