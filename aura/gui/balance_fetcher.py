from __future__ import annotations

import logging

import httpx
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class BalanceWorker(QObject):
    finished = Signal(int, str)  # balance_micros, error_msg

    def __init__(self, base_url: str, api_key: str):
        super().__init__()
        self._base_url = base_url
        self._api_key = api_key

    def run(self):
        try:
            url = self._base_url.rstrip("/") + "/me/balance"
            resp = httpx.get(
                url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                balance_micros = int(data.get("balance_micros", -1))
                self.finished.emit(balance_micros, "")
            else:
                self.finished.emit(-1, f"HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:
            logger.warning("Balance fetch failed: %s", exc)
            self.finished.emit(-1, str(exc))
