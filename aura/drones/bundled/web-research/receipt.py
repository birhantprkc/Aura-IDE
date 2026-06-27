"""Final structured receipt building for the Web Research Drone."""

from __future__ import annotations

from typing import Any

from evidence import _answerable_sources, chunk_useful_evidence
from models import ExtractedAnswer, FetchedSource, SourceTarget
from query import build_search_queries


def _source_status(source: FetchedSource) -> dict[str, Any]:
    status = {
        "title": source.title or source.target.title,
        "url": source.target.url,
        "fetched_at": source.fetched_at,
        "status": "ok" if source.ok else "failed",
        "ok": source.ok,
        "error": source.error,
        "excerpt": source.excerpt,
    }
    if source.final_url and source.final_url != source.target.url:
        status["final_url"] = source.final_url
    return status


def _empty_route(attempted: list[SourceTarget]) -> dict[str, Any]:
    return {
        "type": "none",
        "routes": [],
        "targets": [target.url for target in attempted],
        "attempted_targets": [target.url for target in attempted],
    }


def _build_route_used(
    targets: list[SourceTarget],
    fetched_sources: list[FetchedSource],
    discovery_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    routes = [source.route for source in fetched_sources if source.route]
    if not routes:
        route = _empty_route(targets)
        if discovery_metadata:
            route["browser_discovery"] = discovery_metadata
        return route
    route_type = "mixed" if len(set(routes)) > 1 else routes[0]
    route = {
        "type": route_type,
        "routes": routes,
        "targets": [target.url for target in targets],
        "attempted_targets": [source.target.url for source in fetched_sources],
        "browser_fetches": [
            {
                "url": source.target.url,
                "final_url": source.final_url or source.target.url,
                "status": "ok" if source.ok else "failed",
                "route": source.route,
            }
            for source in fetched_sources
            if source.route == "browser"
        ],
    }
    if discovery_metadata:
        route["browser_discovery"] = discovery_metadata
    return route


def build_result(
    query: str,
    tags: list[str],
    targets: list[SourceTarget],
    fetched_sources: list[FetchedSource],
    extracted: ExtractedAnswer,
    discovery_metadata: dict[str, Any] | None = None,
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
        "route_used": _build_route_used(targets, fetched_sources, discovery_metadata),
    }


def build_failure_receipt(error: str, summary: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": error,
        "summary": summary,
    }
