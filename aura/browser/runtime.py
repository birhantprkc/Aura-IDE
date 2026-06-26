"""Shared Playwright browser runtime lifecycle."""

from __future__ import annotations

import os
import sys

from aura.resources import get_resource_path


class BrowserRuntime:
    """Manages the Playwright browser startup, lifecycle, and teardown.

    Create an instance, call ``start()``, then use ``context`` for
    browsing.  Call ``close()`` when done.
    """

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._pw = None
        self._browser = None
        self._context = None
        self._unavailable_reason = ""

    @property
    def unavailable_reason(self) -> str:
        """The reason the runtime is unavailable, or empty string."""
        return self._unavailable_reason

    @property
    def context(self):  # -> playwright.sync_api.BrowserContext | None
        """The active BrowserContext, or None if not started."""
        return self._context

    def start(self) -> bool:
        """Launch Playwright browser and create a browsing context.

        Returns True on success.  On failure sets ``_unavailable_reason``
        and returns False — never raises.
        """
        try:
            try:
                import playwright.sync_api  # noqa: F401
            except ImportError as exc:
                self._unavailable_reason = str(exc)
                return False

            # Frozen/packaged detection
            if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS") or "__compiled__" in globals():
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(get_resource_path("ms-playwright"))

            self._pw = playwright.sync_api.sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=self._headless)
            self._context = self._browser.new_context()
            return True
        except Exception as exc:
            self._unavailable_reason = str(exc)
            # Tear down partial state — we are already in the error path
            if self._context is not None:
                self._context.close()
                self._context = None
            if self._browser is not None:
                self._browser.close()
                self._browser = None
            if self._pw is not None:
                self._pw.stop()
                self._pw = None
            return False

    def close(self) -> None:
        """Shut down the browser and clean up resources."""
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._pw is not None:
            self._pw.stop()
            self._pw = None
