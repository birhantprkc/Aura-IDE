"""Command shim for the bundled Web Research Drone."""

from __future__ import annotations

from pathlib import Path
import sys

_DRONE_DIR = Path(__file__).resolve().parent
if str(_DRONE_DIR) not in sys.path:
    sys.path.insert(0, str(_DRONE_DIR))

from fetching import discover_candidate_sources, discover_sources, discover_sources_with_gaps, fetch_sources
from models import EvidenceChunk, ExtractedAnswer, FetchedSource, ResearchQuestion, SourceTarget
from query import (
    _parse_query_from_goal,
    build_search_queries,
    classify_query,
    parse_research_query,
)
from receipt import build_failure_receipt, build_result
from research_pipeline import extract_answer, run_query
from research_pipeline import main as _run_pipeline
from schedule import extract_schedule_answer, schedule_subject_from_query

__all__ = [
    "EvidenceChunk",
    "ExtractedAnswer",
    "FetchedSource",
    "ResearchQuestion",
    "SourceTarget",
    "_parse_query_from_goal",
    "build_failure_receipt",
    "build_result",
    "build_search_queries",
    "classify_query",
    "discover_candidate_sources",
    "discover_sources",
    "discover_sources_with_gaps",
    "extract_answer",
    "extract_schedule_answer",
    "fetch_sources",
    "main",
    "parse_research_query",
    "run_query",
    "schedule_subject_from_query",
]


def main() -> None:
    _run_pipeline()


if __name__ == "__main__":
    main()
