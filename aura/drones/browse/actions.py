"""Playwright action helpers for browse drone — click and fill candidates."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def click_candidate(page, candidate) -> tuple[bool, str | None]:
    """Click a browse candidate element and wait for network idle.

    Returns (True, None) on success, (False, error_message) on failure.
    """
    try:
        page.click(f'[data-aura-browse-id="{candidate.id}"]')
        page.wait_for_timeout(500)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            logger.debug("wait_for_load_state timed out after click on %s", candidate.id)
        return True, None
    except Exception as exc:
        return False, str(exc)


def fill_candidate(page, candidate, value: str) -> tuple[bool, str | None]:
    """Fill a form field candidate with the given value.

    Returns (True, None) on success, (False, error_message) on failure.
    """
    try:
        page.fill(f'[data-aura-browse-id="{candidate.id}"]', value)
        return True, None
    except Exception as exc:
        return False, str(exc)
