"""Session manager — tracks connected devices and routes messages."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class DeviceSession:
    """Data stored per connected device."""
    ws: WebSocket
    device_type: str = "desktop"
    display_name: str = ""
    device_name: str = ""
    last_seen: str = ""
    authenticated: bool = False
    token_payload: dict | None = None


class SessionManager:
    """Tracks WebSocket connections for desktops and phones."""

    TICKET_TTL = 300

    def __init__(self) -> None:
        self._sessions: dict[str, DeviceSession] = {}
        self._tickets: dict[str, dict] = {}
        self._paired_phones: dict[str, str] = {}

    def register(self, device_id: str, ws: WebSocket, device_type: str = "desktop",
                 display_name: str = "") -> None:
        """Register a device connection."""
        self._sessions[device_id] = DeviceSession(
            ws=ws,
            device_type=device_type,
            display_name=display_name or device_id,
            last_seen=datetime.now().isoformat(),
        )
        logger.info("[Relay] device registered: %s (%s)", device_id, device_type)

    def unregister(self, device_id: str) -> None:
        """Remove a device connection."""
        self._sessions.pop(device_id, None)
        logger.info("[Relay] device unregistered: %s", device_id)

    def is_online(self, device_id: str) -> bool:
        return device_id in self._sessions

    def get_ws(self, device_id: str) -> WebSocket | None:
        entry = self._sessions.get(device_id)
        return entry.ws if entry else None

    async def send_to(self, device_id: str, data: str) -> bool:
        """Send a raw JSON string to a connected device."""
        ws = self.get_ws(device_id)
        if ws is None:
            return False
        try:
            await ws.send_text(data)
            return True
        except Exception as exc:
            logger.warning("[Relay] send_to %s failed: %s", device_id, exc)
            self.unregister(device_id)
            return False

    def list_online(self, device_type: str | None = None) -> list[dict]:
        """List connected devices, optionally filtered by type."""
        result = []
        for did, session in self._sessions.items():
            if device_type and session.device_type != device_type:
                continue
            result.append({
                "device_id": did,
                "display_name": session.display_name,
                "device_type": session.device_type,
                "last_seen": session.last_seen,
            })
        return result

    @property
    def online_count(self) -> int:
        return len(self._sessions)

    def set_authenticated(self, device_id: str, token_payload: dict) -> None:
        """Mark a device as authenticated with its JWT payload."""
        session = self._sessions.get(device_id)
        if session:
            session.authenticated = True
            session.token_payload = token_payload

    def is_authenticated(self, device_id: str) -> bool:
        """Check if a device has completed pairing."""
        session = self._sessions.get(device_id)
        return session is not None and session.authenticated

    def set_device_name(self, device_id: str, name: str) -> None:
        """Set a friendly name for a device."""
        session = self._sessions.get(device_id)
        if session:
            session.device_name = name

    def get_device_name(self, device_id: str) -> str:
        """Get the friendly name of a device."""
        session = self._sessions.get(device_id)
        return session.device_name if session else ""

    # --- Ticket store ---

    def register_ticket(self, ticket: str, data: dict) -> None:
        """Store a pairing ticket with expiration."""
        data["expires_at"] = time.time() + self.TICKET_TTL
        self._tickets[ticket] = data
        logger.info("[Relay] ticket registered: %s", ticket)

    def resolve_ticket(self, ticket: str) -> dict | None:
        """Resolve a ticket, returning its data. Removes expired tickets.

        Returns None if the ticket doesn't exist or has expired.
        """
        data = self._tickets.get(ticket)
        if data is None:
            return None
        if time.time() > data.get("expires_at", 0):
            self._tickets.pop(ticket, None)
            logger.info("[Relay] ticket expired: %s", ticket)
            return None
        self._tickets.pop(ticket, None)
        return data

    # --- Phone-desktop pairing ---

    def set_paired(self, phone_id: str, desktop_id: str) -> None:
        """Record a phone-to-desktop pairing."""
        self._paired_phones[phone_id] = desktop_id
        logger.info("[Relay] paired: phone=%s -> desktop=%s", phone_id, desktop_id)

    def get_paired_desktop(self, phone_id: str) -> str | None:
        """Return the desktop_id this phone is paired with, or None."""
        return self._paired_phones.get(phone_id)

    def get_paired_phones(self, desktop_id: str) -> list[str]:
        """Return all phone_ids paired with this desktop."""
        return [pid for pid, did in self._paired_phones.items() if did == desktop_id]
