"""Evidence chunking, relevance scoring, and source-quality gaps."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from models import EvidenceChunk, FetchedSource, TIMEZONES
from query import _query_terms


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
        from schedule import _normalize_team_label, _normalize_time, _schedule_matches_from_text

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
