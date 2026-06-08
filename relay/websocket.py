"""WebSocket endpoint for device connections."""
from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from relay.protocol import validate_envelope
from relay.auth import verify_token
from relay.sessions import SessionManager

logger = logging.getLogger(__name__)


async def handle_websocket(ws: WebSocket, sessions: SessionManager) -> None:
    """Handle a WebSocket connection from a desktop or phone.

    Phase 0-1: accepts any connection, uses a simple handshake.
    Phase 4: validates JWT token during handshake.
    """
    await ws.accept()

    # Simple handshake: first message should be { "type": "hello", "device_id": "...", ... }
    device_id = ""
    try:
        raw = await ws.receive_text()
        hello = json.loads(raw)
        if hello.get("type") == "hello":
            device_id = hello.get("device_id", "")
            device_type = hello.get("device_type", "desktop")
            display_name = hello.get("display_name", device_id)
        else:
            await ws.send_text(json.dumps({"type": "error", "payload": {"message": "Expected hello"}}))
            await ws.close()
            return
    except Exception:
        await ws.close()
        return

    if not device_id:
        await ws.send_text(json.dumps({"type": "error", "payload": {"message": "Missing device_id"}}))
        await ws.close()
        return

    sessions.register(device_id, ws, device_type, display_name)

    # Desktops are trusted on the LAN: they own the pairing-code authority,
    # so we mark them authenticated as soon as they connect. Phones must
    # complete the pair handshake before non-skip messages route.
    if device_type == "desktop":
        sessions.set_authenticated(device_id, {"role": "desktop", "desktop_id": device_id})
        logger.info("[Relay] desktop %s auto-authenticated", device_id)

    # Send welcome
    await ws.send_text(json.dumps({
        "type": "welcome",
        "payload": {"device_id": device_id, "online_count": sessions.online_count},
    }))

    # Forward online list to everyone
    await _broadcast_online(sessions)

    # If hello had a token, verify and mark as authenticated (phones)
    token = hello.get("token", "")
    if token and device_type != "desktop":
        token_payload = verify_token(token)
        if token_payload:
            sessions.set_authenticated(device_id, token_payload)
            logger.info("[Relay] device %s authenticated via hello token", device_id)
        else:
            logger.warning("[Relay] device %s sent invalid token in hello", device_id)

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)

            if not validate_envelope(msg):
                await ws.send_text(json.dumps({
                    "type": "error",
                    "payload": {"message": "Invalid envelope"},
                }))
                continue

            msg_type = msg.get("type")

            # Auth gate: non-pair messages require authentication
            AUTH_SKIP_TYPES = {
                "hello", "welcome", "error", "system.online_list",
                "pair.connect", "pair.cancel", "pair.verify",
                "pair.confirmed", "pair.error",
            }
            if msg_type not in AUTH_SKIP_TYPES:
                if not sessions.is_authenticated(device_id):
                    await ws.send_text(json.dumps({
                        "id": f"evt_{uuid4().hex[:12]}",
                        "type": "auth.error",
                        "desktop_id": "",
                        "project_id": "",
                        "conversation_id": "",
                        "in_response_to": msg.get("id", ""),
                        "payload": {"message": "Device not paired. Send pair.connect to authenticate."},
                    }))
                    continue

            if msg_type == "ticket.register":
                # Desktop generates a ticket for phone to use in pair.connect
                payload = msg.get("payload", {})
                ticket = payload.get("ticket", "")
                code = payload.get("code", "")
                project_id = payload.get("project_id", "")
                conversation_id = payload.get("conversation_id", "")
                desktop_name = payload.get("desktop_name", "")

                if not ticket:
                    await ws.send_text(json.dumps({
                        "id": f"evt_{uuid4().hex[:12]}",
                        "type": "error",
                        "desktop_id": "",
                        "project_id": "",
                        "conversation_id": "",
                        "in_response_to": msg.get("id", ""),
                        "payload": {"message": "Missing ticket"},
                    }))
                    continue

                sessions.register_ticket(ticket, {
                    "desktop_id": device_id,
                    "code": code,
                    "desktop_name": desktop_name,
                    "project_id": project_id,
                    "conversation_id": conversation_id,
                })
                await ws.send_text(json.dumps({
                    "id": f"evt_{uuid4().hex[:12]}",
                    "type": "ticket.registered",
                    "desktop_id": device_id,
                    "project_id": "",
                    "conversation_id": "",
                    "in_response_to": msg.get("id", ""),
                    "payload": {"ticket": ticket},
                }))
                continue

            if msg_type == "pair.connect":
                # Phone wants to pair with a desktop
                payload = msg.get("payload", {})
                phone_id = msg.get("device_id", "") or device_id
                phone_name = payload.get("device_name", "Phone")

                ticket = payload.get("ticket", "")
                if ticket:
                    # Ticket-based pairing: resolve ticket to find desktop
                    ticket_data = sessions.resolve_ticket(ticket)
                    if ticket_data is None:
                        await ws.send_text(json.dumps({
                            "id": f"evt_{uuid4().hex[:12]}",
                            "type": "pair.error",
                            "desktop_id": "",
                            "project_id": "",
                            "conversation_id": "",
                            "in_response_to": msg.get("id", ""),
                            "payload": {"message": "Invalid or expired ticket"},
                        }))
                        continue
                    pairing_code = ticket_data.get("code", "")
                    target_desktop_id = ticket_data.get("desktop_id", "")
                else:
                    # Manual code-based pairing (backward compat)
                    pairing_code = payload.get("code", "")
                    target_desktop_id = msg.get("desktop_id", "")

                if not pairing_code or not target_desktop_id:
                    await ws.send_text(json.dumps({
                        "id": f"evt_{uuid4().hex[:12]}",
                        "type": "pair.error",
                        "desktop_id": "",
                        "project_id": "",
                        "conversation_id": "",
                        "in_response_to": msg.get("id", ""),
                        "payload": {"message": "Missing pairing code or desktop_id"},
                    }))
                    continue

                # Forward to the desktop for verification
                verify_msg = {
                    "id": f"pair_verify_{uuid4().hex[:12]}",
                    "type": "pair.verify",
                    "desktop_id": target_desktop_id,
                    "project_id": "",
                    "conversation_id": "",
                    "in_response_to": "",
                    "payload": {
                        "code": pairing_code,
                        "phone_id": phone_id,
                        "device_name": phone_name,
                        "original_msg_id": msg.get("id", ""),
                    },
                }
                ok = await sessions.send_to(target_desktop_id, json.dumps(verify_msg))
                if not ok:
                    await ws.send_text(json.dumps({
                        "id": f"evt_{uuid4().hex[:12]}",
                        "type": "pair.error",
                        "desktop_id": "",
                        "project_id": "",
                        "conversation_id": "",
                        "in_response_to": msg.get("id", ""),
                        "payload": {"message": "Desktop not online"},
                    }))
                continue

            if msg_type == "pair.paired_devices":
                # Desktop queries which phones are paired with it
                paired = sessions.get_paired_phones(device_id)
                await ws.send_text(json.dumps({
                    "id": f"evt_{uuid4().hex[:12]}",
                    "type": "pair.paired_devices",
                    "desktop_id": device_id,
                    "project_id": "",
                    "conversation_id": "",
                    "in_response_to": msg.get("id", ""),
                    "payload": {"phone_ids": paired},
                }))
                continue

            if msg_type == "desktop.list":
                online = sessions.list_online()
                await ws.send_text(json.dumps({
                    "id": f"evt_{uuid4().hex[:12]}",
                    "type": "system.online_list",
                    "desktop_id": "",
                    "project_id": "",
                    "conversation_id": "",
                    "in_response_to": msg.get("id", ""),
                    "payload": {"devices": online},
                }))
                continue

            if msg_type == "pair.confirmed" and sessions.is_online(device_id):
                # Desktop confirmed a pairing — forward to phone and mark phone as authenticated
                payload = msg.get("payload", {})
                phone_id = payload.get("phone_id", "")
                token = payload.get("token", "")
                phone_name = payload.get("device_name", "Phone")

                if phone_id and token:
                    token_payload = verify_token(token)
                    if token_payload:
                        sessions.set_authenticated(phone_id, token_payload)
                        sessions.set_device_name(phone_id, phone_name)

                # Record pairing and add scope info before forwarding to phone
                sessions.set_paired(phone_id, device_id)
                confirmed_msg = json.loads(raw)
                confirmed_msg["payload"]["scoped_to"] = device_id

                await sessions.send_to(phone_id, json.dumps(confirmed_msg))
                continue

            # Route to target desktop
            target = msg.get("desktop_id", "")
            if target and sessions.is_online(target):
                # Scope check: phones can only route to their paired desktop
                if sessions.is_authenticated(device_id):
                    sender_session = sessions._sessions.get(device_id)
                    if sender_session and sender_session.token_payload:
                        sender_role = sender_session.token_payload.get("role", "")
                        if sender_role == "phone":
                            paired = sessions.get_paired_desktop(device_id)
                            if paired != target:
                                await ws.send_text(json.dumps({
                                    "id": f"evt_{uuid4().hex[:12]}",
                                    "type": "error",
                                    "desktop_id": "",
                                    "project_id": "",
                                    "conversation_id": "",
                                    "in_response_to": msg.get("id", ""),
                                    "payload": {"message": "Phone is not paired with this desktop"},
                                }))
                                continue

                msg["sender_device_id"] = device_id
                ok = await sessions.send_to(target, json.dumps(msg))
                if not ok:
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "payload": {"message": f"Failed to route to {target}"},
                    }))
            else:
                await ws.send_text(json.dumps({
                    "type": "error",
                    "payload": {"message": "Desktop not online"},
                }))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("[Relay] WS error: %s", exc)
    finally:
        sessions.unregister(device_id)
        await _broadcast_online(sessions)


async def _broadcast_online(sessions: SessionManager) -> None:
    """Broadcast updated online device list to all connected clients."""
    online = sessions.list_online()
    payload = json.dumps({
        "id": "evt_sys_online",
        "type": "system.online_list",
        "desktop_id": "",
        "project_id": "",
        "conversation_id": "",
        "in_response_to": "",
        "payload": {"devices": online},
    })
    # Don't await each — fire-and-forget-ish
    for did in list(sessions._sessions.keys()):
        await sessions.send_to(did, payload)
