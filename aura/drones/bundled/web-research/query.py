"""Query parsing and search-query construction for web research."""

from __future__ import annotations

import re

from models import ResearchQuestion, STOPWORDS


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
