"""Reply helpers — build protocol envelopes without Qt or websocket."""
from __future__ import annotations

import logging

from aura.companion.protocol import make_envelope

logger = logging.getLogger(__name__)


def build_reply_envelope(
    msg: dict,
    msg_type: str,
    payload: dict,
    *,
    project_id: str = "",
    conversation_id: str = "",
) -> dict | None:
    """Build a reply envelope addressed back to the sender device.

    Returns the envelope dict, or None if the message has no sender_device_id
    (in which case a warning is logged — the caller handles the None).
    """
    sender_device_id = msg.get("sender_device_id", "")
    if not sender_device_id:
        logger.warning(
            "[Companion] cannot build reply to %s: missing sender_device_id",
            msg_type,
        )
        return None
    return make_envelope(
        msg_type,
        payload,
        desktop_id=sender_device_id,
        project_id=project_id,
        conversation_id=conversation_id,
        in_response_to=msg.get("id", ""),
    )
