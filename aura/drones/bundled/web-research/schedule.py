"""Schedule-specific fast path for the Web Research Drone."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from evidence import _evidence_item
from models import ExtractedAnswer, FetchedSource, SourceTarget, TEAM_ALIASES, TIMEZONES


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
