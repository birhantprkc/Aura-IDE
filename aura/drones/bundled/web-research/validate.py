"""Validation and confidence enforcement for synthesized research answers."""

from __future__ import annotations

from models import ExtractedAnswer, FetchedSource


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
