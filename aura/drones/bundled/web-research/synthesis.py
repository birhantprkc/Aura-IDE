"""Model-backed and local evidence synthesis."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from typing import Any

from evidence import (
    _evidence_item,
    _score_text_against_query,
    _source_conflict_gaps,
    _split_sentences,
    _stale_source_gaps,
)
from models import EvidenceChunk, ExtractedAnswer
from query import _query_terms


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
