"""Browser-backed search discovery for the Web Research Drone."""

from __future__ import annotations

import base64
import html as html_lib
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from models import SourceTarget

try:
    from aura.browser.runtime import BrowserRuntime
    from aura.drones.browse.profiles import ensure_profile_dir

    BROWSER_SUPPORTED = True
except ImportError:
    BrowserRuntime = None  # type: ignore[assignment]
    ensure_profile_dir = None  # type: ignore[assignment]
    BROWSER_SUPPORTED = False


SEARCH_BLOCKED_GAP = "Browser search was blocked by a CAPTCHA or verification page."
PAGE_BLOCKED_ERROR = "Page was blocked by a CAPTCHA or verification page."


@dataclass
class BrowserSearchResult:
    targets: list[SourceTarget] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    attempted: bool = False
    blocked: bool = False
    route_metadata: dict[str, Any] = field(default_factory=dict)


def read_browser_settings() -> dict[str, Any]:
    """Read browser settings from the colocated drone manifest."""
    permissions: dict[str, Any] = {}
    manifest_path = Path(__file__).with_name("drone.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_permissions = manifest.get("permissions", {})
        if isinstance(raw_permissions, dict):
            permissions = raw_permissions
    except (OSError, json.JSONDecodeError):
        permissions = {}

    raw_profile = permissions.get("browser_profile", "research")
    browser_profile = raw_profile.strip() if isinstance(raw_profile, str) else ""
    return {
        "browser_profile": browser_profile or None,
        "visible": bool(permissions.get("visible", False)),
    }


def create_browser_runtime():
    """Create a BrowserRuntime using the drone's browser profile settings."""
    if not BROWSER_SUPPORTED or BrowserRuntime is None:
        return None

    settings = read_browser_settings()
    profile_name = settings.get("browser_profile")
    visible = bool(settings.get("visible", False))
    profile_path = None
    if profile_name and ensure_profile_dir is not None:
        profile_path = ensure_profile_dir(str(profile_name))
    return BrowserRuntime(headless=not visible, user_data_dir=profile_path)


def _search_url(search_query: str) -> str:
    encoded = urllib.parse.quote_plus(search_query)
    return f"https://www.bing.com/search?q={encoded}"


def _clean_label(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _search_host(host: str) -> bool:
    host = host.lower().split(":", 1)[0]
    search_hosts = (
        "bing.com",
        "www.bing.com",
        "google.com",
        "www.google.com",
        "duckduckgo.com",
        "html.duckduckgo.com",
        "search.yahoo.com",
        "search.brave.com",
    )
    return host in search_hosts or any(host.endswith(f".{item}") for item in search_hosts)


def _decode_bing_u(value: str) -> str:
    if not value:
        return ""
    candidate = value
    if candidate.startswith("a1"):
        candidate = candidate[2:]
    try:
        padded = candidate + "=" * (-len(candidate) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="ignore")
    except Exception:
        return ""
    return decoded if decoded.startswith(("http://", "https://")) else ""


def _redirect_target_from_search_url(parsed: urllib.parse.ParseResult) -> str:
    values = urllib.parse.parse_qs(parsed.query)
    for key in ("uddg", "q", "url"):
        for value in values.get(key, []):
            decoded = urllib.parse.unquote(value)
            if decoded.startswith(("http://", "https://")):
                return decoded
    for value in values.get("u", []):
        decoded = _decode_bing_u(value)
        if decoded:
            return decoded
    return ""


def normalize_search_result_url(raw_href: str, base_url: str) -> str:
    """Normalize and filter a candidate URL from a browser search page."""
    href = html_lib.unescape(raw_href or "").strip()
    if not href:
        return ""
    href = urllib.parse.urljoin(base_url, href)
    parsed = urllib.parse.urlparse(href)
    if parsed.scheme not in {"http", "https"}:
        return ""

    if _search_host(parsed.netloc):
        redirected = _redirect_target_from_search_url(parsed)
        if redirected:
            return normalize_search_result_url(redirected, base_url)
        return ""

    clean = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))
    return clean.rstrip("/")


def is_captcha_or_verification_page(title: str, url: str, body_text: str) -> bool:
    """Detect obvious CAPTCHA or bot-verification pages."""
    url_lower = (url or "").lower()
    if any(token in url_lower for token in ("captcha", "/sorry/", "challenge", "verification")):
        return True

    combined = " ".join([title or "", body_text or ""]).lower()
    patterns = (
        "captcha",
        "verify you are human",
        "human verification",
        "are you a robot",
        "unusual traffic",
        "automated queries",
        "complete the security check",
        "complete the challenge",
        "checking your browser",
        "security check to access",
        "detected unusual",
    )
    return any(pattern in combined for pattern in patterns)


def _visible_body_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        try:
            return page.inner_text("body", timeout=5000)
        except Exception:
            return ""


def extract_visible_result_links(page, base_url: str, max_targets: int = 8) -> list[SourceTarget]:
    """Extract visible result links from the current browser DOM."""
    js_code = """
    (maxAnchors) => {
        const anchors = Array.from(document.querySelectorAll('a[href]'));
        const results = [];
        for (const anchor of anchors) {
            if (results.length >= maxAnchors) break;
            const style = window.getComputedStyle(anchor);
            const rect = anchor.getBoundingClientRect();
            if (
                style.display === 'none' ||
                style.visibility === 'hidden' ||
                parseFloat(style.opacity || '1') === 0 ||
                rect.width === 0 ||
                rect.height === 0
            ) {
                continue;
            }
            const text = (anchor.innerText || anchor.textContent || anchor.getAttribute('aria-label') || '').trim();
            results.push({
                href: anchor.href || anchor.getAttribute('href') || '',
                text: text,
            });
        }
        return results;
    }
    """
    try:
        raw_links = page.evaluate(js_code, max_targets * 6)
    except Exception:
        return []

    links: list[SourceTarget] = []
    seen: set[str] = set()
    for raw_link in raw_links:
        if not isinstance(raw_link, dict):
            continue
        url = normalize_search_result_url(str(raw_link.get("href") or ""), base_url)
        if not url or url in seen:
            continue
        seen.add(url)
        label = _clean_label(str(raw_link.get("text") or ""))[:160] or url
        links.append(SourceTarget(url=url, title=label, kind="candidate"))
        if len(links) >= max_targets:
            break
    return links


def discover_with_browser(search_queries: list[str], max_targets: int = 8) -> BrowserSearchResult:
    """Use BrowserRuntime to perform normal browser search and extract candidates."""
    result = BrowserSearchResult()
    if not search_queries:
        return result

    runtime = create_browser_runtime()
    if runtime is None:
        result.gaps.append("Browser search unavailable: BrowserRuntime could not be imported.")
        return result

    try:
        if not runtime.start():
            reason = runtime.unavailable_reason or "Browser runtime did not start."
            result.gaps.append(f"Browser search unavailable: {reason}")
            return result

        result.route_metadata = dict(runtime.route_metadata)
        context = runtime.context
        if context is None:
            result.gaps.append("Browser search unavailable: Browser context was not created.")
            return result
        try:
            context.set_default_navigation_timeout(15000)
        except Exception:
            pass
        page = context.pages[0] if context.pages else context.new_page()

        for search_query in search_queries:
            if len(result.targets) >= max_targets:
                break
            url = _search_url(search_query)
            result.attempted = True
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass
            except Exception as exc:
                result.gaps.append(f"Browser search navigation failed for '{search_query}': {exc}")
                continue

            title = page.title() or ""
            body_text = _visible_body_text(page)
            if is_captcha_or_verification_page(title, page.url, body_text):
                result.blocked = True
                if SEARCH_BLOCKED_GAP not in result.gaps:
                    result.gaps.append(SEARCH_BLOCKED_GAP)
                break

            for target in extract_visible_result_links(
                page,
                page.url or url,
                max_targets=max_targets - len(result.targets),
            ):
                if target.url not in {existing.url for existing in result.targets}:
                    result.targets.append(target)

        if result.attempted and not result.targets and not result.gaps:
            result.gaps.append("Browser search did not return candidate result links.")
        return result
    except Exception as exc:
        result.gaps.append(f"Browser search failed: {exc}")
        return result
    finally:
        try:
            runtime.close()
        except Exception:
            pass
