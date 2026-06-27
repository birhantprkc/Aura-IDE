"""Web Research Drone - live sourced current-info research."""

import datetime as dt
from dataclasses import dataclass, field
import html as html_lib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

try:
    from aura.browser.runtime import BrowserRuntime

    BROWSER_SUPPORTED = True
except ImportError:
    BROWSER_SUPPORTED = False


TIMEZONES = "GMT|UTC|ET|EST|EDT|CT|CST|CDT|MT|MST|MDT|PT|PST|PDT"
TEAM_ALIASES = {
    "ENG": "England",
    "USA": "USA",
}

STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "and",
    "answer",
    "are",
    "because",
    "been",
    "before",
    "being",
    "can",
    "could",
    "current",
    "did",
    "does",
    "doing",
    "for",
    "from",
    "has",
    "have",
    "how",
    "into",
    "is",
    "it",
    "its",
    "latest",
    "more",
    "most",
    "new",
    "now",
    "of",
    "on",
    "or",
    "please",
    "recent",
    "show",
    "tell",
    "than",
    "that",
    "the",
    "their",
    "then",
    "there",
    "this",
    "today",
    "tomorrow",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


@dataclass(frozen=True)
class SourceTarget:
    url: str
    title: str = ""
    kind: str = "web"


@dataclass
class FetchedSource:
    target: SourceTarget
    title: str
    text: str
    fetched_at: str
    ok: bool
    error: str = ""
    excerpt: str = ""
    route: str = "http"
    links: list[SourceTarget] = field(default_factory=list)


@dataclass
class ExtractedAnswer:
    answer: str
    verified_facts: list[str]
    evidence: list[dict[str, Any]]
    gaps: list[str]
    confidence: str


@dataclass(frozen=True)
class ResearchQuestion:
    raw: str
    normalized: str
    tags: list[str]
    terms: list[str]
    search_queries: list[str]


@dataclass(frozen=True)
class EvidenceChunk:
    source_url: str
    title: str
    text: str
    excerpt: str
    score: float
    chunk_index: int


def _parse_query_from_goal(goal: str) -> str | None:
    """Extract the research query from the goal string."""
    if not goal or not goal.strip():
        return None

    lines = goal.split("\n")
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("query:"):
            extracted = stripped[len("query:") :].strip()
            return extracted if extracted else None

    return goal.strip()


def classify_query(query: str) -> list[str]:
    tags: list[str] = []
    lower = query.lower()
    if "today" in lower or "tonight" in lower:
        tags.append("today")
    if "tomorrow" in lower:
        tags.append("tomorrow")
    if "world cup" in lower:
        tags.append("world_cup")
    if any(word in lower for word in ("schedule", "time", "play", "fixtures", "matches", "match", "game")):
        tags.append("schedule")
    if any(word in lower for word in ("latest", "current", "today", "tonight", "tomorrow", "recent", "now")):
        tags.append("current_info")
    if any(word in lower for word in ("latest", "newest", "version", "release")):
        tags.append("version")
    if any(word in lower for word in ("release notes", "changelog", "changed", "changes", "what changed", "fixed", "added")):
        tags.append("release_notes")
    if any(word in lower for word in ("price", "prices", "pricing", "cost", "costs", "$", "token", "tokens")):
        tags.append("pricing")
    if re.search(r"\b(?:ceo|chief executive|president|chair|mayor|governor|minister|leader|head of)\b", lower):
        tags.append("person_role")
        tags.append("current_info")
    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            deduped.append(tag)
    return deduped


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9.+#-]*", query.lower()):
        normalized = token.strip(".-")
        if len(normalized) < 3 or normalized in STOPWORDS:
            continue
        if normalized.endswith("s") and len(normalized) > 4 and not normalized.endswith("ss"):
            normalized = normalized[:-1]
        if normalized not in seen:
            seen.add(normalized)
            terms.append(normalized)
    return terms


def _subject_hint(query: str) -> str:
    """Build a search-friendly subject without turning the answer into a template."""
    cleaned = re.sub(r"https?://\S+", " ", query)
    cleaned = re.sub(r"[?!.]+", " ", cleaned)
    cleaned = re.sub(
        r"\b(?:what|who|when|where|which|is|are|was|were|does|do|did|the|a|an|"
        r"current|latest|newest|price|pricing|cost|version|release|notes|changelog|"
        r"changed|changes|today|tomorrow|now|please|tell|show|me)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or query.strip()


def build_search_queries(query: str, tags: list[str]) -> list[str]:
    queries: list[str] = []
    if "world_cup" in tags and "schedule" in tags:
        queries.append("World Cup matches today schedule")
    queries.append(query.strip())
    subject = _subject_hint(query)
    if "pricing" in tags:
        queries.append(f"{subject} pricing official")
    if "release_notes" in tags:
        queries.append(f"{subject} release notes changelog latest")
    if "version" in tags:
        queries.append(f"{subject} latest version release official")
    if "person_role" in tags:
        queries.append(f"{subject} official leadership current")
    if "schedule" in tags and "world_cup" not in tags:
        queries.append(f"{subject} schedule official")
    if "current_info" in tags and not any(tag in tags for tag in ("pricing", "release_notes", "version", "person_role", "schedule")):
        queries.append(f"{subject} latest current official")

    seen: set[str] = set()
    unique: list[str] = []
    for item in queries:
        normalized = " ".join(item.split())
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique[:5]


def parse_research_query(query: str) -> ResearchQuestion:
    normalized = " ".join(str(query or "").split())
    tags = classify_query(normalized)
    return ResearchQuestion(
        raw=query,
        normalized=normalized,
        tags=tags,
        terms=_query_terms(normalized),
        search_queries=build_search_queries(normalized, tags),
    )


def discover_sources(query: str, tags: list[str]) -> list[SourceTarget]:
    targets: list[SourceTarget] = []
    for direct_url in re.findall(r"https?://[^\s)>\"]+", query):
        targets.append(SourceTarget(url=direct_url.rstrip(".,;"), title=direct_url.rstrip(".,;"), kind="candidate"))

    if "world_cup" in tags and "schedule" in tags:
        targets.append(
            SourceTarget(
                url="https://www.fifa.com/en/match-center",
                title="FIFA Match Centre",
                kind="official_schedule",
            )
        )
        targets.append(
            SourceTarget(
                url="https://www.espn.com/soccer/schedule",
                title="ESPN Soccer Schedule",
                kind="reputable_schedule",
            )
        )

    for search_query in build_search_queries(query, tags):
        encoded = urllib.parse.quote(search_query)
        targets.append(
            SourceTarget(
                url=f"https://html.duckduckgo.com/html/?q={encoded}",
                title=f"Search results for {search_query}",
                kind="search",
            )
        )

    seen: set[str] = set()
    unique: list[SourceTarget] = []
    for target in targets:
        if target.url in seen:
            continue
        seen.add(target.url)
        unique.append(target)
    return unique[:8]


def _empty_route(attempted: list[SourceTarget]) -> dict[str, Any]:
    return {
        "type": "none",
        "routes": [],
        "targets": [target.url for target in attempted],
        "attempted_targets": [target.url for target in attempted],
    }


def _load_mock_fixture() -> dict[str, Any]:
    raw = os.environ.get("_AURA_WEB_RESEARCH_MOCK_FIXTURE", "")
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _search_query_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query_values = urllib.parse.parse_qs(parsed.query).get("q", [])
    return query_values[0] if query_values else ""


def _mock_fixture_results_for_target(fixture: dict[str, Any], target: SourceTarget) -> list[dict[str, Any]]:
    raw_results = fixture.get("results", [])
    if isinstance(raw_results, dict):
        search_query = _search_query_from_url(target.url)
        raw_results = raw_results.get(search_query) or raw_results.get("default") or []
    if not isinstance(raw_results, list):
        return []
    results: list[dict[str, Any]] = []
    for item in raw_results:
        if isinstance(item, str):
            results.append({"url": item, "title": item})
        elif isinstance(item, dict) and isinstance(item.get("url"), str):
            results.append(
                {
                    "url": str(item["url"]),
                    "title": str(item.get("title") or item["url"]),
                }
            )
    return results


def _mock_fixture_page_for_url(fixture: dict[str, Any], url: str) -> dict[str, Any] | None:
    raw_pages = fixture.get("pages", {})
    if not isinstance(raw_pages, dict) or url not in raw_pages:
        return None
    raw_page = raw_pages[url]
    if isinstance(raw_page, str):
        return {"title": url, "text": raw_page, "ok": True}
    if isinstance(raw_page, dict):
        return raw_page
    return None


def _mock_search_page(target: SourceTarget, fetched_at: str, results: list[dict[str, Any]]) -> FetchedSource:
    links = [
        SourceTarget(url=str(result["url"]), title=str(result.get("title") or result["url"]), kind="candidate")
        for result in results
    ]
    text_parts = [f"Search result: {link.title} {link.url}" for link in links]
    text = " ".join(text_parts) or "No mocked search results."
    return FetchedSource(
        target=target,
        title=target.title or "Mock Search",
        text=text,
        fetched_at=fetched_at,
        ok=bool(results),
        error="" if results else "No mocked search results.",
        excerpt=text[:1200],
        route="mock",
        links=links,
    )


def _builtin_mock_results(target: SourceTarget) -> list[dict[str, Any]]:
    query = _search_query_from_url(target.url).lower()
    if "fail" in query or "not found" in query:
        return [{"url": "https://mock.local/fail", "title": "Mock Failure"}]
    if "world cup" in query:
        return [{"url": "https://mock.local/world-cup-schedule", "title": "World Cup Schedule"}]
    if "python" in query and ("version" in query or "latest" in query):
        return [{"url": "https://mock.local/python-latest", "title": "Python Downloads"}]
    if "nuitka" in query:
        return [{"url": "https://mock.local/nuitka-release", "title": "Nuitka Changelog"}]
    if "gpt-4.1" in query or "gpt 4.1" in query or "openai" in query and "price" in query:
        return [{"url": "https://mock.local/openai-pricing", "title": "OpenAI API Pricing"}]
    if "microsoft" in query and "ceo" in query:
        return [{"url": "https://mock.local/microsoft-leadership", "title": "Microsoft Leadership"}]
    return [{"url": "https://mock.local/no-clear-answer", "title": "Mock Search Result"}]


def _builtin_mock_page(url: str) -> dict[str, Any] | None:
    pages: dict[str, dict[str, Any]] = {
        "https://mock.local/fail": {
            "ok": False,
            "title": "Mock Failure",
            "text": "",
            "error": "HTTP fetch error: 404 Not Found",
        },
        "https://mock.local/world-cup-schedule": {
            "title": "World Cup Schedule",
            "text": "World Cup Matches Today: USA vs ENG 8:00 PM GMT",
        },
        "https://mock.local/python-latest": {
            "title": "Python Downloads",
            "text": "Latest Python release: Python 3.14.0 is the newest stable version.",
        },
        "https://mock.local/nuitka-release": {
            "title": "Nuitka Changelog",
            "text": (
                "Nuitka 2.7.12 is the latest release. "
                "Changes in Nuitka 2.7.12 include improved standalone packaging and fixes for Python 3.14."
            ),
        },
        "https://mock.local/openai-pricing": {
            "title": "OpenAI API Pricing",
            "text": "GPT-4.1 pricing is $2.00 per 1M input tokens and $8.00 per 1M output tokens.",
        },
        "https://mock.local/microsoft-leadership": {
            "title": "Microsoft Leadership",
            "text": "Satya Nadella is Chairman and Chief Executive Officer of Microsoft.",
        },
        "https://mock.local/no-clear-answer": {
            "title": "Mock Search Result",
            "text": "This page mentions general background information but does not provide the requested current answer.",
        },
    }
    return pages.get(url)


def _mock_fetch_source(target: SourceTarget, fetched_at: str) -> FetchedSource | None:
    fixture = _load_mock_fixture()
    fixture_page = _mock_fixture_page_for_url(fixture, target.url)
    if fixture_page is not None:
        ok = bool(fixture_page.get("ok", True))
        text = str(fixture_page.get("text", ""))
        error = str(fixture_page.get("error", ""))
        links = [
            SourceTarget(url=str(link.get("url")), title=str(link.get("title") or link.get("url")), kind="candidate")
            for link in fixture_page.get("links", [])
            if isinstance(link, dict) and isinstance(link.get("url"), str)
        ]
        return FetchedSource(
            target=target,
            title=str(fixture_page.get("title") or target.title),
            text=text,
            fetched_at=fetched_at,
            ok=ok,
            error="" if ok else error or "Mocked source failed.",
            excerpt=text[:1200],
            route="mock",
            links=links,
        )
    if target.kind == "search" and fixture:
        return _mock_search_page(target, fetched_at, _mock_fixture_results_for_target(fixture, target))

    if os.environ.get("_AURA_MOCK_WEB_RESEARCH") != "1":
        return None

    lower_url = target.url.lower()
    builtin_page = _builtin_mock_page(target.url)
    if builtin_page is not None:
        ok = bool(builtin_page.get("ok", True))
        text = str(builtin_page.get("text", ""))
        return FetchedSource(
            target=target,
            title=str(builtin_page.get("title") or target.title),
            text=text,
            fetched_at=fetched_at,
            ok=ok,
            error="" if ok else str(builtin_page.get("error") or "Mocked source failed."),
            excerpt=text[:1200],
            route="mock",
        )
    if target.kind == "search":
        return _mock_search_page(target, fetched_at, _builtin_mock_results(target))
    if "fail" in lower_url or "not%20found" in lower_url:
        return FetchedSource(
            target=target,
            title=target.title or "Mock Failure",
            text="",
            fetched_at=fetched_at,
            ok=False,
            error="HTTP fetch error: 404 Not Found",
            route="http",
        )
    if "fifa.com" in lower_url:
        text = "World Cup Matches Today: USA vs ENG 8:00 PM GMT"
        return FetchedSource(
            target=target,
            title=target.title or "FIFA Mock",
            text=text,
            fetched_at=fetched_at,
            ok=True,
            excerpt=text,
            route="http",
        )
    if "world%20cup" in lower_url or "world cup" in lower_url:
        text = "Search result: World Cup Matches Today: USA vs ENG 8:00 PM GMT"
        return FetchedSource(
            target=target,
            title=target.title or "Mock Search",
            text=text,
            fetched_at=fetched_at,
            ok=True,
            excerpt=text,
            route="http",
        )

    text = "Mocked search result. Evidence exists, but no concise answer is extractable."
    return FetchedSource(
        target=target,
        title=target.title or "Mock Search",
        text=text,
        fetched_at=fetched_at,
        ok=True,
        excerpt=text,
        route="http",
    )


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _normalize_result_url(raw_href: str, base_url: str) -> str:
    href = html_lib.unescape(raw_href or "").strip()
    if not href:
        return ""
    href = urllib.parse.urljoin(base_url, href)
    parsed = urllib.parse.urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        uddg_values = urllib.parse.parse_qs(parsed.query).get("uddg", [])
        if uddg_values:
            href = urllib.parse.unquote(uddg_values[0])
            parsed = urllib.parse.urlparse(href)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if any(host in parsed.netloc.lower() for host in ("duckduckgo.com", "google.com", "bing.com")):
        return ""
    clean = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))
    return clean.rstrip("/")


def _extract_links_from_html(html: str, base_url: str) -> list[SourceTarget]:
    links: list[SourceTarget] = []
    seen: set[str] = set()
    anchor_pattern = re.compile(
        r"(?is)<a\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<label>.*?)</a>"
    )
    for match in anchor_pattern.finditer(html):
        url = _normalize_result_url(match.group("href"), base_url)
        if not url or url in seen:
            continue
        label = _strip_html(match.group("label"))[:160] or url
        seen.add(url)
        links.append(SourceTarget(url=url, title=label, kind="candidate"))
        if len(links) >= 10:
            break
    return links


def _extract_links_from_text(text: str) -> list[SourceTarget]:
    links: list[SourceTarget] = []
    seen: set[str] = set()
    for raw in re.findall(r"https?://[^\s<>()\"']+", text):
        url = raw.rstrip(".,;]")
        if url in seen:
            continue
        seen.add(url)
        links.append(SourceTarget(url=url, title=url, kind="candidate"))
        if len(links) >= 10:
            break
    return links


def _fetch_source(target: SourceTarget, now: dt.datetime) -> FetchedSource:
    fetched_at = now.isoformat()
    mocked = _mock_fetch_source(target, fetched_at)
    if mocked is not None:
        return mocked

    browser_error = ""
    if BROWSER_SUPPORTED:
        runtime = None
        try:
            runtime = BrowserRuntime(headless=True)
            if runtime.start():
                page = runtime.context.pages[0] if runtime.context.pages else runtime.context.new_page()
                page.goto(target.url, wait_until="domcontentloaded", timeout=15000)
                title = page.title() or target.title
                text = page.locator("body").inner_text(timeout=5000)
                links: list[SourceTarget] = []
                if target.kind == "search":
                    try:
                        raw_links = page.locator("a").evaluate_all(
                            "(els) => els.map((a) => ({href: a.href, text: a.innerText || a.textContent || ''}))"
                        )
                        seen: set[str] = set()
                        for raw_link in raw_links:
                            if not isinstance(raw_link, dict):
                                continue
                            url = _normalize_result_url(str(raw_link.get("href") or ""), target.url)
                            if not url or url in seen:
                                continue
                            seen.add(url)
                            label = re.sub(r"\s+", " ", str(raw_link.get("text") or url)).strip()
                            links.append(SourceTarget(url=url, title=label[:160] or url, kind="candidate"))
                            if len(links) >= 10:
                                break
                    except Exception:
                        links = []
                excerpt = re.sub(r"\s+", " ", text).strip()[:1200]
                if text.strip():
                    return FetchedSource(
                        target=target,
                        title=title,
                        text=text,
                        fetched_at=fetched_at,
                        ok=True,
                        excerpt=excerpt,
                        route="browser",
                        links=links,
                    )
                browser_error = "Browser fetch returned no readable body text."
            else:
                browser_error = "Browser runtime did not start."
        except Exception as exc:
            browser_error = f"Browser fetch error: {exc}"
        finally:
            if runtime is not None:
                try:
                    runtime.close()
                except Exception:
                    pass

    req = urllib.request.Request(
        target.url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Aura/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8", errors="ignore")
        title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        title = _strip_html(title_match.group(1)) if title_match else target.title
        links = _extract_links_from_html(html, target.url) if target.kind == "search" else []
        text = _strip_html(html)
        return FetchedSource(
            target=target,
            title=title or target.title,
            text=text,
            fetched_at=fetched_at,
            ok=bool(text),
            error="" if text else "Fetched page had no readable body text.",
            excerpt=text[:1200],
            route="browser_http_fallback" if browser_error else "http",
            links=links,
        )
    except Exception as exc:
        error = f"HTTP fetch error: {exc}"
        if browser_error:
            error = f"{browser_error}; {error}"
        return FetchedSource(
            target=target,
            title=target.title,
            text="",
            fetched_at=fetched_at,
            ok=False,
            error=error,
            route="http",
        )


def fetch_sources(targets: list[SourceTarget], now: dt.datetime | None = None) -> list[FetchedSource]:
    now = now or dt.datetime.now().astimezone()
    fetched: list[FetchedSource] = []
    for target in targets[:8]:
        fetched.append(_fetch_source(target, now))
    return fetched


def discover_candidate_sources(
    fetched_sources: list[FetchedSource],
    existing_targets: list[SourceTarget],
) -> list[SourceTarget]:
    seen = {target.url for target in existing_targets}
    candidates: list[SourceTarget] = []
    for source in fetched_sources:
        links = list(source.links)
        if source.target.kind == "search" and not links:
            links = _extract_links_from_text(source.text)
        for link in links:
            if link.url in seen:
                continue
            seen.add(link.url)
            candidates.append(link)
            if len(candidates) >= 8:
                return candidates
    return candidates


def _answerable_sources(ok_sources: list[FetchedSource]) -> list[FetchedSource]:
    non_search = [source for source in ok_sources if source.target.kind != "search"]
    return non_search if non_search else ok_sources


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9$])", normalized)
    if len(parts) == 1:
        parts = re.split(r"\s+[•*-]\s+", normalized)
    return [part.strip(" -•") for part in parts if part.strip(" -•")]


def _score_text_against_query(text: str, query: str, tags: list[str], terms: list[str] | None = None) -> float:
    lower = text.lower()
    terms = terms if terms is not None else _query_terms(query)
    score = 0.0
    for term in terms:
        if term and term in lower:
            score += 1.4 if len(term) > 4 else 1.0
    if "version" in tags:
        if re.search(r"\b\d+(?:\.\d+){1,4}(?:[a-z]+\d*)?\b", text, flags=re.IGNORECASE):
            score += 2.0
        if re.search(r"\b(?:latest|current|newest|stable|release|released|version)\b", lower):
            score += 1.5
    if "release_notes" in tags:
        if re.search(r"\b(?:change|changed|changes|added|fixed|improved|removed|deprecated|release notes|changelog)\b", lower):
            score += 2.0
    if "pricing" in tags:
        if re.search(r"[$€£]\s*\d|\b(?:price|pricing|cost|per|token|tokens|input|output|usd)\b", lower):
            score += 2.4
    if "person_role" in tags:
        if re.search(r"\b(?:ceo|chief executive|president|chair|leader|head of|serves as|appointed|named)\b", lower):
            score += 2.0
    if "schedule" in tags:
        if re.search(rf"\b(?:vs\.?|v\.?|versus|at|(?:{TIMEZONES}))\b", text, flags=re.IGNORECASE):
            score += 1.5
        if re.search(r"\b(?:[01]?\d|2[0-3])(?::[0-5]\d)\s*(?:AM|PM|am|pm)?\b", text):
            score += 1.5
    if "current_info" in tags and re.search(r"\b(?:current|latest|today|updated|as of|announced|now)\b", lower):
        score += 0.8
    return score


def chunk_useful_evidence(fetched_sources: list[FetchedSource]) -> list[EvidenceChunk]:
    chunks: list[EvidenceChunk] = []
    for source in fetched_sources:
        if not source.ok or not source.text.strip():
            continue
        sentences = _split_sentences(source.text)
        if not sentences:
            continue
        chunk_index = 0
        buffer: list[str] = []
        for sentence in sentences:
            candidate = " ".join(buffer + [sentence]).strip()
            if len(candidate) <= 900:
                buffer.append(sentence)
                continue
            if buffer:
                text = " ".join(buffer).strip()
                chunks.append(
                    EvidenceChunk(
                        source_url=source.target.url,
                        title=source.title or source.target.title,
                        text=text,
                        excerpt=text[:900],
                        score=0.0,
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1
            buffer = [sentence]
        if buffer:
            text = " ".join(buffer).strip()
            chunks.append(
                EvidenceChunk(
                    source_url=source.target.url,
                    title=source.title or source.target.title,
                    text=text,
                    excerpt=text[:900],
                    score=0.0,
                    chunk_index=chunk_index,
                )
            )
    return chunks


def select_relevant_evidence(
    query: str,
    fetched_sources: list[FetchedSource],
    tags: list[str],
    limit: int = 12,
) -> list[EvidenceChunk]:
    terms = _query_terms(query)
    scored: list[EvidenceChunk] = []
    for chunk in chunk_useful_evidence(fetched_sources):
        combined = f"{chunk.title}. {chunk.text}"
        score = _score_text_against_query(combined, query, tags, terms)
        if score <= 0:
            continue
        scored.append(
            EvidenceChunk(
                source_url=chunk.source_url,
                title=chunk.title,
                text=chunk.text,
                excerpt=chunk.excerpt,
                score=score,
                chunk_index=chunk.chunk_index,
            )
        )
    scored.sort(key=lambda item: (-item.score, item.source_url, item.chunk_index))
    return scored[:limit]


def _evidence_item(source_url: str, excerpt: str, fact: str) -> dict[str, Any]:
    return {
        "source_url": source_url,
        "excerpt": re.sub(r"\s+", " ", excerpt).strip()[:900],
        "supports_fact": fact,
    }


def _years_in_text(text: str) -> list[int]:
    years: list[int] = []
    for match in re.finditer(r"\b(20[0-4]\d|19[7-9]\d)\b", text):
        try:
            years.append(int(match.group(1)))
        except ValueError:
            continue
    return years


def _stale_source_gaps(
    query: str,
    tags: list[str],
    chunks: list[EvidenceChunk],
    now: dt.datetime,
) -> list[str]:
    if not any(tag in tags for tag in ("current_info", "version", "release_notes", "pricing", "person_role")):
        return []
    current_year = now.year
    gaps: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        years = _years_in_text(chunk.text)
        if not years:
            continue
        newest = max(years)
        if newest <= current_year - 2 and chunk.source_url not in seen:
            seen.add(chunk.source_url)
            gaps.append(
                f"Potentially stale source: {chunk.source_url} only showed dates up to {newest} for a current-information query."
            )
    return gaps


def _answer_values_from_text(text: str, tags: list[str]) -> tuple[str, ...]:
    if "pricing" in tags:
        values = re.findall(
            r"[$€£]\s*\d+(?:\.\d+)?(?:\s*/\s*[A-Za-z0-9 ]+|\s+per\s+[A-Za-z0-9 .-]+)?",
            text,
            flags=re.IGNORECASE,
        )
        if values:
            return tuple(re.sub(r"\s+", " ", value).strip().lower() for value in values)
    if "person_role" in tags:
        patterns = [
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4})\s+(?:is|serves as|remains|became|was named|has been named)\s+(?:[^.]{0,90})\b(?:CEO|Chief Executive)",
            r"\b(?:CEO|Chief Executive Officer)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return (re.sub(r"\s+", " ", match.group(1)).strip().lower(),)
    if "schedule" in tags:
        values = []
        for match in _schedule_matches_from_text(text):
            values.append(f"{_normalize_team_label(match.group('label'))} {_normalize_time(match.group('time'))}".lower())
        if values:
            return tuple(values)
    version_values = re.findall(r"\b\d+(?:\.\d+){1,4}(?:[a-z]+\d*)?\b", text, flags=re.IGNORECASE)
    if version_values and any(tag in tags for tag in ("version", "release_notes", "current_info")):
        return (version_values[0].lower(),)
    return ()


def _source_conflict_gaps(query: str, tags: list[str], chunks: list[EvidenceChunk]) -> list[str]:
    _ = query
    values_by_source: dict[str, tuple[str, ...]] = {}
    for chunk in chunks:
        values = _answer_values_from_text(chunk.text, tags)
        if values and chunk.source_url not in values_by_source:
            values_by_source[chunk.source_url] = values
    unique_values = {values for values in values_by_source.values()}
    if len(unique_values) <= 1:
        return []
    rendered = [
        f"{url} says {', '.join(values)}"
        for url, values in list(values_by_source.items())[:4]
    ]
    return [f"Source conflict: {'; '.join(rendered)}."]


def schedule_subject_from_query(query: str) -> str:
    """Return a concise schedule subject for answer wording."""
    normalized = " ".join(str(query or "").strip().lower().split())
    if "world cup" in normalized:
        return "World Cup matches"
    if "play next" in normalized or "next match" in normalized or "next game" in normalized:
        return "Next match"

    match = re.search(
        r"\b(?:does|do|will|is|are)\s+(?P<team>[A-Za-z0-9 .&'-]{1,40}?)\s+play\b",
        str(query or ""),
        flags=re.IGNORECASE,
    )
    if match:
        team = re.sub(r"\s+", " ", match.group("team")).strip(" ?")
        team = re.sub(r"^(?:the)\s+", "", team, flags=re.IGNORECASE).strip()
        if team:
            return f"{team} match"

    return "Matches"


def _normalize_team_label(label: str) -> str:
    parts = re.split(r"\s+(vs\.?|v\.?|versus)\s+", label, flags=re.IGNORECASE)
    if len(parts) >= 3:
        home = _normalize_team_name(parts[0])
        away = _normalize_team_name(parts[2])
        return f"{home} vs {away}"
    return re.sub(r"\s+", " ", label).strip()


def _normalize_team_name(name: str) -> str:
    clean = re.sub(r"\s+", " ", name).strip(" .:-")
    clean = re.sub(r"\s+\bat\b$", "", clean, flags=re.IGNORECASE).strip()
    return TEAM_ALIASES.get(clean.upper(), clean)


def _normalize_time(value: str) -> str:
    clean = re.sub(r"\s+", " ", value).strip()
    suffix_match = re.search(rf"\b(?:{TIMEZONES})\b$", clean, flags=re.IGNORECASE)
    suffix = suffix_match.group(0).upper() if suffix_match else ""
    if suffix:
        clean = clean[: suffix_match.start()].strip()
    ampm_match = re.search(r"\b(?:AM|PM)\b$", clean, flags=re.IGNORECASE)
    ampm = ampm_match.group(0).upper() if ampm_match else ""
    if ampm:
        clean = clean[: ampm_match.start()].strip()
    result = clean
    if ampm:
        result = f"{result} {ampm}"
    if suffix:
        result = f"{result} {suffix}"
    return result


def _schedule_matches_from_text(text: str) -> list[re.Match[str]]:
    time_pattern = (
        r"(?P<time>(?:[01]?\d|2[0-3])(?::[0-5]\d)\s*(?:AM|PM|am|pm)?"
        rf"(?:\s*(?:{TIMEZONES}))?|(?:[1-9]|1[0-2])\s*(?:AM|PM|am|pm)"
        rf"(?:\s*(?:{TIMEZONES}))?)"
    )
    team = r"[A-Z][A-Za-z0-9 .&'()-]{1,40}"
    pattern = re.compile(
        rf"(?P<label>{team}\s+(?:vs\.?|v\.?|versus)\s+{team})\s*(?:[-:|,]|\bat\b)?\s*{time_pattern}",
        flags=re.IGNORECASE,
    )
    return list(pattern.finditer(text))


def _excerpt_around(text: str, start: int, end: int, radius: int = 220) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def extract_schedule_answer(
    query: str,
    fetched_sources: list[FetchedSource] | str,
    now: dt.datetime,
) -> ExtractedAnswer | tuple[str, list[str], list[dict[str, Any]], list[str], str]:
    """Extract one or more schedule entries from fetched evidence.

    A string input is accepted for older direct unit tests and returns the
    historical tuple shape.
    """
    legacy_text_input = isinstance(fetched_sources, str)
    if legacy_text_input:
        fetched_list = [
            FetchedSource(
                target=SourceTarget("about:legacy", "Evidence"),
                title="Evidence",
                text=str(fetched_sources),
                fetched_at=now.isoformat(),
                ok=bool(str(fetched_sources).strip()),
                excerpt=str(fetched_sources)[:1200],
            )
        ]
    else:
        fetched_list = fetched_sources

    entries: list[tuple[str, str, str, str]] = []
    evidence: list[dict[str, Any]] = []
    useful_text_seen = False

    for source in fetched_list:
        if not source.ok or not source.text.strip():
            continue
        useful_text_seen = True
        for match in _schedule_matches_from_text(source.text):
            label = _normalize_team_label(match.group("label"))
            time_string = _normalize_time(match.group("time"))
            fact = f"{label} is listed at {time_string}."
            if any(existing_fact == fact for _label, _time, existing_fact, _url in entries):
                continue
            entries.append((label, time_string, fact, source.target.url))
            evidence.append(
                _evidence_item(source.target.url, _excerpt_around(source.text, match.start(), match.end()), fact)
            )

    if not entries:
        no_parse_evidence: list[dict[str, Any]] = []
        for source in fetched_list:
            if source.ok and source.excerpt:
                no_parse_evidence.append(_evidence_item(source.target.url, source.excerpt, ""))
        result = ExtractedAnswer(
            answer="",
            verified_facts=[],
            evidence=no_parse_evidence[:2],
            gaps=[
                "No extractable schedule match and time were found in the fetched evidence."
                if useful_text_seen
                else "No evidence text was available to parse."
            ],
            confidence="low" if useful_text_seen else "none",
        )
        if legacy_text_input:
            return result.answer, result.verified_facts, result.evidence, result.gaps, result.confidence
        return result

    date_label = "today" if "today" in query.lower() else "tomorrow" if "tomorrow" in query.lower() else "requested date"
    subject = schedule_subject_from_query(query)
    rendered = [f"{label} at {time_string}" for label, time_string, _fact, _url in entries]
    if subject == "Next match":
        answer = f"{subject}: {rendered[0]}."
    else:
        answer = f"{subject} {date_label}: {'; '.join(rendered)}."

    facts = [fact for _label, _time, fact, _url in entries]
    gaps: list[str] = []
    if any(re.search(rf"\b(?:{TIMEZONES})\b", time_string, flags=re.IGNORECASE) for _label, time_string, _fact, _url in entries):
        gaps.append("Timezone conversion was not performed; the source timezone was preserved.")
    else:
        gaps.append("The source evidence did not include a timezone, so no timezone conversion was performed.")

    sources_by_fact: dict[str, set[str]] = {}
    for _label, _time, fact, url in entries:
        sources_by_fact.setdefault(fact, set()).add(url)
    if len({fact for _label, _time, fact, _url in entries}) != len(entries):
        gaps.append("Duplicate schedule facts appeared in fetched evidence.")

    result = ExtractedAnswer(
        answer=answer,
        verified_facts=facts,
        evidence=evidence,
        gaps=gaps,
        confidence="medium",
    )
    if legacy_text_input:
        return result.answer, result.verified_facts, result.evidence, result.gaps, result.confidence
    return result


MODEL_SYNTHESIS_SYSTEM_PROMPT = """You are Aura's web research synthesis step.
You must answer only from the fetched evidence supplied in the user message.
Do not use model memory, training data, unstated assumptions, or outside facts.
If the evidence does not directly support an answer, return an empty answer and explain the gap.
Return only valid JSON matching this exact schema:
{
  "answer": "string",
  "verified_facts": ["string"],
  "evidence": [{"source_url": "string", "excerpt": "string", "supports_fact": "string"}],
  "gaps": ["string"],
  "confidence": "high|medium|low|none"
}
Every verified fact must have an evidence item whose supports_fact exactly equals that fact.
Use high confidence only for strong, non-conflicting support from multiple relevant sources.
Use medium confidence for direct support from at least one relevant source.
Use low confidence for partial, ambiguous, stale, or conflicting evidence.
Use none when no usable source evidence is available."""


def _json_object_from_text(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _evidence_pack_for_model(query: str, chunks: list[EvidenceChunk], now: dt.datetime) -> dict[str, Any]:
    return {
        "query": query,
        "fetched_at": now.isoformat(),
        "evidence": [
            {
                "source_url": chunk.source_url,
                "title": chunk.title,
                "excerpt": chunk.excerpt,
            }
            for chunk in chunks
        ],
    }


def _configured_model_synthesis(
    query: str,
    chunks: list[EvidenceChunk],
    now: dt.datetime,
) -> ExtractedAnswer | None:
    if os.environ.get("_AURA_MOCK_WEB_RESEARCH") == "1":
        return None
    if os.environ.get("_AURA_WEB_RESEARCH_DISABLE_MODEL") == "1":
        return None
    if not chunks:
        return None
    try:
        from aura.client.events import ApiError, ContentDelta, Done
        from aura.providers.registry import provider_registry
        from aura.settings import load_settings
    except Exception:
        return None

    try:
        settings = load_settings()
        provider = getattr(settings, "worker_provider", None) or getattr(settings, "provider", "")
        if not provider or not provider_registry.has(provider):
            return None
        model = getattr(settings, "default_worker_model", "") or getattr(settings, "default_model", "")
        thinking = getattr(settings, "default_worker_thinking", "off")
        client = provider_registry.create_client(provider)
        messages = [
            {"role": "system", "content": MODEL_SYNTHESIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(_evidence_pack_for_model(query, chunks, now), ensure_ascii=False),
            },
        ]
        content_parts: list[str] = []
        for event in client.stream(
            messages=messages,
            tools=None,
            model=model,
            thinking=thinking,
            temperature=0.0,
        ):
            if isinstance(event, ApiError):
                return None
            if isinstance(event, ContentDelta):
                content_parts.append(event.text)
            if isinstance(event, Done):
                full_content = event.full_message.get("content")
                if isinstance(full_content, str) and full_content.strip():
                    content_parts = [full_content]
                break
    except Exception:
        return None

    parsed = _json_object_from_text("".join(content_parts))
    if parsed is None:
        return None
    return _validated_extracted_from_payload(parsed, chunks)


def _validated_extracted_from_payload(
    payload: dict[str, Any],
    chunks: list[EvidenceChunk],
) -> ExtractedAnswer | None:
    answer = payload.get("answer")
    facts_raw = payload.get("verified_facts")
    evidence_raw = payload.get("evidence")
    gaps_raw = payload.get("gaps")
    confidence = payload.get("confidence")
    if not isinstance(answer, str) or not isinstance(facts_raw, list) or not isinstance(evidence_raw, list):
        return None
    if not isinstance(gaps_raw, list):
        gaps_raw = []
    if confidence not in {"high", "medium", "low", "none"}:
        confidence = "low"

    chunk_urls = {chunk.source_url for chunk in chunks}
    facts = [str(fact).strip() for fact in facts_raw if isinstance(fact, str) and fact.strip()]
    evidence: list[dict[str, Any]] = []
    for fact in facts:
        matched: dict[str, Any] | None = None
        for item in evidence_raw:
            if not isinstance(item, dict):
                continue
            source_url = item.get("source_url")
            excerpt = item.get("excerpt")
            supports_fact = item.get("supports_fact")
            if source_url not in chunk_urls or not isinstance(excerpt, str) or supports_fact != fact:
                continue
            if any(excerpt.strip() in chunk.text or excerpt.strip() in chunk.excerpt for chunk in chunks if chunk.source_url == source_url):
                matched = _evidence_item(str(source_url), excerpt, fact)
                break
        if matched is None:
            for chunk in chunks:
                if _score_text_against_query(chunk.text, fact, [], _query_terms(fact)) > 0:
                    matched = _evidence_item(chunk.source_url, chunk.excerpt, fact)
                    break
        if matched is None:
            continue
        evidence.append(matched)

    supported_facts = [item["supports_fact"] for item in evidence if item.get("supports_fact")]
    facts = [fact for fact in facts if fact in supported_facts]
    gaps = [str(gap) for gap in gaps_raw if isinstance(gap, str) and gap.strip()]
    return ExtractedAnswer(
        answer=answer.strip() if facts else "",
        verified_facts=facts,
        evidence=evidence,
        gaps=gaps,
        confidence=str(confidence),
    )


def _candidate_fact_sentences(query: str, tags: list[str], chunks: list[EvidenceChunk]) -> list[tuple[str, EvidenceChunk, float]]:
    terms = _query_terms(query)
    candidates: list[tuple[str, EvidenceChunk, float]] = []
    for chunk in chunks:
        for sentence in _split_sentences(chunk.text):
            score = _score_text_against_query(sentence, query, tags, terms)
            if score <= 0:
                continue
            candidates.append((sentence.strip(), chunk, score + chunk.score * 0.15))
    candidates.sort(key=lambda item: (-item[2], item[1].source_url, item[0]))
    deduped: list[tuple[str, EvidenceChunk, float]] = []
    seen: set[str] = set()
    for sentence, chunk, score in candidates:
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append((sentence, chunk, score))
    return deduped


def _local_synthesis(
    query: str,
    tags: list[str],
    chunks: list[EvidenceChunk],
    now: dt.datetime,
) -> ExtractedAnswer:
    if not chunks:
        return ExtractedAnswer(
            answer="",
            verified_facts=[],
            evidence=[],
            gaps=[
                "No fetched source contained enough query-relevant evidence.",
                "Model synthesis was unavailable; used conservative local evidence extraction.",
            ],
            confidence="low",
        )

    candidates = _candidate_fact_sentences(query, tags, chunks)
    threshold = 2.2 if any(tag in tags for tag in ("version", "release_notes", "pricing", "person_role", "schedule")) else 1.8
    facts: list[str] = []
    evidence: list[dict[str, Any]] = []
    for sentence, chunk, score in candidates:
        if score < threshold:
            continue
        fact = sentence if sentence.endswith((".", "!", "?")) else f"{sentence}."
        if fact in facts:
            continue
        facts.append(fact)
        evidence.append(_evidence_item(chunk.source_url, chunk.excerpt, fact))
        max_facts = 5 if "release_notes" in tags else 3
        if len(facts) >= max_facts:
            break

    gaps = [
        "Model synthesis was unavailable; used conservative local evidence extraction."
    ]
    gaps.extend(_stale_source_gaps(query, tags, chunks, now))
    conflict_gaps = _source_conflict_gaps(query, tags, chunks)
    gaps.extend(conflict_gaps)

    if not facts:
        preview = [_evidence_item(chunk.source_url, chunk.excerpt, "") for chunk in chunks[:2]]
        return ExtractedAnswer(
            answer="",
            verified_facts=[],
            evidence=preview,
            gaps=gaps + ["Fetched evidence did not clearly support a direct answer to the query."],
            confidence="low",
        )

    answer = " ".join(facts)
    source_count = len({item["source_url"] for item in evidence})
    confidence = "high" if source_count >= 2 and not conflict_gaps else "medium"
    if conflict_gaps:
        confidence = "low"
    return ExtractedAnswer(
        answer=answer,
        verified_facts=facts,
        evidence=evidence,
        gaps=gaps,
        confidence=confidence,
    )


def _enforce_confidence_rules(
    extracted: ExtractedAnswer,
    ok_sources: list[FetchedSource],
) -> ExtractedAnswer:
    source_urls = {source.target.url for source in ok_sources}
    evidence = [
        item
        for item in extracted.evidence
        if isinstance(item, dict)
        and isinstance(item.get("source_url"), str)
        and item.get("source_url") in source_urls
        and isinstance(item.get("excerpt"), str)
        and "supports_fact" in item
    ]
    supported = {str(item.get("supports_fact")) for item in evidence if item.get("supports_fact")}
    facts = [fact for fact in extracted.verified_facts if fact in supported]
    answer = extracted.answer if facts else ""
    confidence = extracted.confidence
    if confidence not in {"high", "medium", "low", "none"}:
        confidence = "low"
    if not ok_sources:
        confidence = "none"
        answer = ""
        facts = []
        evidence = []
    elif not answer:
        confidence = "low" if confidence != "none" else "none"
        facts = []
    elif confidence in {"medium", "high"} and (not facts or not evidence or not source_urls):
        confidence = "low"
    if any("source conflict" in gap.lower() for gap in extracted.gaps) and confidence == "high":
        confidence = "medium"
    if any("source conflict" in gap.lower() for gap in extracted.gaps) and confidence == "medium":
        confidence = "low"
    return ExtractedAnswer(
        answer=answer,
        verified_facts=facts,
        evidence=evidence,
        gaps=extracted.gaps,
        confidence=confidence,
    )


def extract_answer(
    query: str,
    tags: list[str],
    fetched_sources: list[FetchedSource],
    now: dt.datetime,
) -> ExtractedAnswer:
    ok_sources = [source for source in fetched_sources if source.ok and source.text.strip()]
    if not ok_sources:
        return ExtractedAnswer(
            answer="",
            verified_facts=[],
            evidence=[],
            gaps=["No useful evidence was fetched."],
            confidence="none",
        )

    evidence_sources = _answerable_sources(ok_sources)
    selected_chunks = select_relevant_evidence(query, evidence_sources, tags)

    if "schedule" in tags:
        extracted = extract_schedule_answer(query, evidence_sources, now)
        assert isinstance(extracted, ExtractedAnswer)
        if extracted.answer:
            extracted.gaps.extend(_stale_source_gaps(query, tags, selected_chunks, now))
            extracted.gaps.extend(_source_conflict_gaps(query, tags, selected_chunks))
            return _enforce_confidence_rules(extracted, ok_sources)

    model_extracted = _configured_model_synthesis(query, selected_chunks, now)
    if model_extracted is not None:
        model_extracted.gaps.extend(_stale_source_gaps(query, tags, selected_chunks, now))
        model_extracted.gaps.extend(_source_conflict_gaps(query, tags, selected_chunks))
        return _enforce_confidence_rules(model_extracted, ok_sources)

    local = _local_synthesis(query, tags, selected_chunks, now)
    if "schedule" in tags and not local.answer:
        schedule_attempt = extract_schedule_answer(query, evidence_sources, now)
        assert isinstance(schedule_attempt, ExtractedAnswer)
        local.gaps = schedule_attempt.gaps + [gap for gap in local.gaps if gap not in schedule_attempt.gaps]
        if not local.evidence and schedule_attempt.evidence:
            local.evidence = schedule_attempt.evidence
    return _enforce_confidence_rules(local, ok_sources)


def _source_status(source: FetchedSource) -> dict[str, Any]:
    return {
        "title": source.title or source.target.title,
        "url": source.target.url,
        "fetched_at": source.fetched_at,
        "status": "ok" if source.ok else "failed",
        "ok": source.ok,
        "error": source.error,
        "excerpt": source.excerpt,
    }


def _build_route_used(targets: list[SourceTarget], fetched_sources: list[FetchedSource]) -> dict[str, Any]:
    routes = [source.route for source in fetched_sources if source.route]
    if not routes:
        return _empty_route(targets)
    route_type = "mixed" if len(set(routes)) > 1 else routes[0]
    return {
        "type": route_type,
        "routes": routes,
        "targets": [target.url for target in targets],
        "attempted_targets": [source.target.url for source in fetched_sources],
    }


def build_result(
    query: str,
    tags: list[str],
    targets: list[SourceTarget],
    fetched_sources: list[FetchedSource],
    extracted: ExtractedAnswer,
) -> dict[str, Any]:
    failed = [source for source in fetched_sources if not source.ok]
    successful = [source for source in fetched_sources if source.ok and source.text.strip()]
    gaps: list[str] = []
    for source in failed:
        gaps.append(f"Could not reach {source.target.url}: {source.error}")
    gaps.extend(extracted.gaps)
    if failed and successful:
        gaps.append("At least one source failed, but another source supplied extractable evidence.")
    if not successful:
        gaps.append("No useful evidence was fetched from attempted sources.")

    trace = [
        {"step": "parse_goal", "status": "completed"},
        {"step": "classify_query", "status": "completed", "tags": tags},
        {"step": "build_search_queries", "status": "completed", "queries": build_search_queries(query, tags)},
        {"step": "discover_sources", "status": "completed", "targets": [target.url for target in targets]},
        {
            "step": "fetch_sources",
            "status": "completed",
            "attempted": len(fetched_sources),
            "succeeded": len(successful),
            "failed": len(failed),
        },
        {
            "step": "chunk_useful_evidence",
            "status": "completed",
            "chunks": len(chunk_useful_evidence(_answerable_sources(successful))),
        },
        {"step": "select_relevant_evidence", "status": "completed"},
        {"step": "synthesize_answer", "status": "completed", "confidence": extracted.confidence},
        {"step": "build_result", "status": "completed"},
    ]

    confidence = extracted.confidence
    if not extracted.answer and confidence not in {"none", "low"}:
        confidence = "low"
    if not successful:
        confidence = "none"

    return {
        "ok": True,
        "summary": "Completed live web research." if successful else "Web research completed without usable evidence.",
        "query": query,
        "answer": extracted.answer,
        "verified_facts": extracted.verified_facts,
        "sources": [_source_status(source) for source in fetched_sources],
        "evidence": extracted.evidence,
        "gaps": gaps,
        "confidence": confidence,
        "trace": trace,
        "route_used": _build_route_used(targets, fetched_sources),
    }


def build_failure_receipt(error: str, summary: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": error,
        "summary": summary,
    }


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        payload: dict[str, Any] = {}
    else:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            result = build_failure_receipt(
                f"Invalid JSON input: {exc}",
                "Web Research Drone could not run because the input was not valid JSON.",
            )
            print(json.dumps(result))
            return

    goal = payload.get("goal", "")
    query = _parse_query_from_goal(goal)
    if query is None:
        result = build_failure_receipt(
            "query is required",
            "Web Research Drone could not run because no query was provided.",
        )
        print(json.dumps(result))
        return

    now = dt.datetime.now().astimezone()
    parsed = parse_research_query(query)
    tags = parsed.tags
    targets = discover_sources(query, tags)
    initial_sources = fetch_sources(targets, now)
    candidate_targets = discover_candidate_sources(initial_sources, targets)
    candidate_sources = fetch_sources(candidate_targets, now) if candidate_targets else []
    targets = targets + candidate_targets
    fetched_sources = initial_sources + candidate_sources
    extracted = extract_answer(query, tags, fetched_sources, now)
    result = build_result(query, tags, targets, fetched_sources, extracted)
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        result = build_failure_receipt(
            str(exc),
            f"Web Research Drone encountered an error: {exc}",
        )
        print(json.dumps(result))
