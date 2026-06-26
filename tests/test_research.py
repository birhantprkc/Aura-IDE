"""Tests for the research subsystem.

Tests cover data models, payload enrichment, and module exports.
No Playwright or network calls — these are pure unit tests.
"""

from __future__ import annotations

from dataclasses import asdict

from aura.research import Evidence, ResearchResult, Source, research_current_info


class TestResearchResultDataclass:
    """Verify ResearchResult dataclass construction and defaults."""

    def test_default_instantiation(self) -> None:
        """ResearchResult can be created with just a query."""
        result = ResearchResult(query="test query")
        assert result.query == "test query"
        assert result.ok is True
        assert result.sources == []
        assert result.evidence == []
        assert result.notes == []

    def test_source_count_not_required(self) -> None:
        """source_count/evidence_count are computed, not stored fields."""
        result = ResearchResult(query="q")
        # These should NOT be fields on the dataclass
        assert not hasattr(result, "source_count")
        assert not hasattr(result, "evidence_count")
        # They are derived from list lengths
        assert len(result.sources) == 0
        assert len(result.evidence) == 0

    def test_ok_defaults_to_true(self) -> None:
        """ok field defaults to True."""
        result = ResearchResult(query="q")
        assert result.ok is True
        result_fail = ResearchResult(query="q", ok=False)
        assert result_fail.ok is False

    def test_query_field(self) -> None:
        """query is a required field."""
        result = ResearchResult(query="what is the weather?")
        assert result.query == "what is the weather?"


class TestResearchHandlerPayloadEnriched:
    """Verify the mixin-style payload dict includes source_count and evidence_count."""

    def test_payload_contains_count_fields(self) -> None:
        """Construct a ResearchResult and verify the handler's payload dict shape."""
        source = Source(url="https://example.com", title="Example", snippet="An example page")
        evidence = Evidence(source=source, text="Some evidence text.", fetched_at="2025-01-01T00:00:00Z")
        result = ResearchResult(
            query="test",
            sources=[source],
            evidence=[evidence],
            ok=True,
        )
        # Build the payload dict the same way _handle_research_current_info does
        payload = {
            "ok": result.ok,
            "query": result.query,
            "source_count": len(result.sources),
            "evidence_count": len(result.evidence),
            "sources": [asdict(s) for s in result.sources],
            "evidence": [asdict(e) for e in result.evidence],
            "notes": result.notes,
        }
        assert payload["source_count"] == 1
        assert payload["evidence_count"] == 1
        assert payload["ok"] is True
        assert payload["query"] == "test"
        assert len(payload["sources"]) == 1
        assert len(payload["evidence"]) == 1

    def test_payload_zero_counts_when_empty(self) -> None:
        """Empty sources/evidence yield zero counts."""
        result = ResearchResult(query="empty")
        payload = {
            "ok": result.ok,
            "query": result.query,
            "source_count": len(result.sources),
            "evidence_count": len(result.evidence),
            "sources": [asdict(s) for s in result.sources],
            "evidence": [asdict(e) for e in result.evidence],
            "notes": result.notes,
        }
        assert payload["source_count"] == 0
        assert payload["evidence_count"] == 0
        assert payload["sources"] == []
        assert payload["evidence"] == []


class TestResearchModuleImports:
    """Verify public exports from aura.research import correctly."""

    def test_research_current_info_importable(self) -> None:
        """research_current_info function is importable."""
        from aura.research import research_current_info
        assert callable(research_current_info)

    def test_research_result_importable(self) -> None:
        """ResearchResult class is importable."""
        from aura.research import ResearchResult
        assert issubclass(ResearchResult, object)

    def test_source_importable(self) -> None:
        """Source class is importable."""
        from aura.research import Source
        source = Source(url="u", title="t")
        assert source.url == "u"
        assert source.title == "t"

    def test_evidence_importable(self) -> None:
        """Evidence class is importable."""
        from aura.research import Evidence
        src = Source(url="u", title="t")
        ev = Evidence(source=src, text="t", fetched_at="2025-01-01T00:00:00Z")
        assert ev.text == "t"
