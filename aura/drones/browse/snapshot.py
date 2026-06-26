"""Page snapshot helpers for browse drone — candidate extraction and snapshot capture."""

from __future__ import annotations

import logging
import re

from aura.drones.browse.models import BrowseCandidate, BrowseSnapshot

logger = logging.getLogger(__name__)


def extract_candidates(page, max_candidates: int = 30) -> list[BrowseCandidate]:
    """Discover interactive elements on the page via JS evaluation.

    Assigns ``data-aura-browse-id`` attributes on each candidate so that
    subsequent Playwright selectors can target them.
    """
    js_code = """
    (maxCandidates) => {
        const selectors = [
            'a[href]',
            'button',
            'input:not([type="hidden"])',
            'textarea',
            'select',
            '[role="button"]',
            '[role="link"]',
            '[role="textbox"]',
            '[role="combobox"]',
            '[role="checkbox"]',
            '[role="radio"]',
            '[role="searchbox"]',
            '[role="menuitem"]',
            '[role="option"]',
            '[role="tab"]',
            '[role="switch"]',
            '[onclick]',
            '[tabindex]:not([tabindex="-1"])'
        ];
        const all = document.querySelectorAll(selectors.join(','));
        const results = [];
        let count = 0;
        for (const el of all) {
            if (count >= maxCandidates) break;

            // Visibility check
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            if (
                style.display === 'none' ||
                style.visibility === 'hidden' ||
                parseFloat(style.opacity) === 0 ||
                rect.width === 0 ||
                rect.height === 0
            ) {
                continue;
            }

            const id = 'c' + count;
            el.setAttribute('data-aura-browse-id', id);

            const tag = el.tagName.toLowerCase();
            let role = el.getAttribute('role') || '';
            if (!role) {
                if (tag === 'a') {
                    role = 'link';
                } else if (tag === 'button') {
                    role = 'button';
                } else if (tag === 'textarea') {
                    role = 'textbox';
                } else if (tag === 'select') {
                    role = 'combobox';
                } else if (tag === 'input') {
                    const inputType = (el.getAttribute('type') || 'text').toLowerCase();
                    role = inputType === 'checkbox' ? 'checkbox' :
                           inputType === 'radio' ? 'radio' :
                           inputType === 'submit' || inputType === 'button' ? 'button' :
                           inputType === 'search' ? 'searchbox' :
                           'textbox';
                }
            }

            // Label resolution: aria-label > name > placeholder > title > textContent
            let label = el.getAttribute('aria-label') || '';
            if (!label) {
                label = el.getAttribute('name') || '';
            }
            if (!label) {
                label = el.getAttribute('placeholder') || '';
            }
            if (!label) {
                label = el.getAttribute('title') || '';
            }
            if (!label && el.textContent) {
                label = el.textContent.trim().substring(0, 100);
            }

            const enabled = !el.disabled;
            let href = '';
            if (tag === 'a') {
                href = el.getAttribute('href') || '';
            }
            let input_type = '';
            if (tag === 'input') {
                input_type = el.getAttribute('type') || 'text';
            } else if (tag === 'textarea') {
                input_type = 'textarea';
            }

            results.push({
                id: id,
                role: role,
                tag: tag,
                label: label,
                enabled: enabled,
                visible: true,
                href: href,
                input_type: input_type,
            });
            count++;
        }
        return results;
    }
    """
    try:
        raw_candidates = page.evaluate(js_code, max_candidates)
    except Exception:
        logger.exception("Failed to extract candidates via JS evaluation")
        return []

    candidates: list[BrowseCandidate] = []
    for rc in raw_candidates:
        candidates.append(
            BrowseCandidate(
                id=rc.get("id", ""),
                role=rc.get("role", ""),
                tag=rc.get("tag", ""),
                label=rc.get("label", ""),
                enabled=rc.get("enabled", True),
                visible=rc.get("visible", True),
                href=rc.get("href", ""),
                input_type=rc.get("input_type", ""),
            )
        )
    return candidates


def capture_snapshot(page, max_candidates: int = 30) -> BrowseSnapshot:
    """Capture the current page state as a BrowseSnapshot."""
    url = page.url
    title = page.title()
    # Normalize body inner_text: collapse whitespace, strip, cap at 2000
    body_text = page.inner_text("body")
    body_text = re.sub(r"\s+", " ", body_text).strip()
    body_excerpt = body_text[:2000]
    candidates = extract_candidates(page, max_candidates=max_candidates)
    candidate_dicts = [c.to_dict() for c in candidates]
    return BrowseSnapshot(
        url=url,
        title=title,
        body_excerpt=body_excerpt,
        candidates=candidate_dicts,
        candidate_count=len(candidates),
    )


def find_candidate(
    candidates: list[BrowseCandidate], text: str
) -> BrowseCandidate | None:
    """Find the best visible, enabled candidate by substring label match.

    Uses case-insensitive substring matching.  Prefers exact match first,
    then shortest label among matches (most specific).
    """
    text_lower = text.lower()
    matches: list[BrowseCandidate] = []
    for c in candidates:
        if not c.visible or not c.enabled:
            continue
        if text_lower in c.label.lower():
            matches.append(c)
    if not matches:
        return None
    # Prefer exact match, then shortest label
    exact = [m for m in matches if m.label.lower() == text_lower]
    if exact:
        return min(exact, key=lambda m: len(m.label))
    return min(matches, key=lambda m: len(m.label))
