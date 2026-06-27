"""Tests for the bundled Web Research Drone (Phase 4)."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from aura.drones.store import DroneStore
from aura.drones.sync_runner import run_read_only_drone_sync


def _load_web_research_main():
    path = (
        Path(__file__).resolve().parent.parent
        / "aura"
        / "drones"
        / "bundled"
        / "web-research"
        / "main.py"
    )
    spec = importlib.util.spec_from_file_location("web_research_main_for_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_aura_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aura.drones.store.aura_root", lambda: tmp_path / "aura_root")
    monkeypatch.setenv("_AURA_MOCK_WEB_RESEARCH", "1")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def web_research_folder(tmp_path: Path) -> Path:
    bundled = (
        Path(__file__).resolve().parent.parent
        / "aura"
        / "drones"
        / "bundled"
        / "web-research"
    )
    assert bundled.is_dir(), f"Source drone folder not found at {bundled}"

    target = (
        tmp_path
        / "aura_root"
        / "aura"
        / "drones"
        / "bundled"
        / "web-research"
    )
    target.mkdir(parents=True)

    (target / "drone.json").write_text(
        (bundled / "drone.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for source_file in bundled.glob("*.py"):
        (target / source_file.name).write_text(
            source_file.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return target


@pytest.fixture
def drone(workspace: Path, web_research_folder: Path) -> DroneStore:
    d = DroneStore.load_drone(workspace, "web-research")
    assert d is not None, "web-research drone should be loadable from the store"
    return d


# ---------------------------------------------------------------------------
# Store / manifest tests
# ---------------------------------------------------------------------------


class TestStoreLoading:
    def test_web_research_loads_from_store(self, workspace: Path, drone: DroneStore) -> None:
        assert drone.id == "web-research"
        assert drone.kind == "command"
        assert drone.write_policy == "read_only"
        assert drone.entrypoint["protocol"] == "json-stdio"

    def test_web_research_appears_in_list_drones(
        self, workspace: Path, web_research_folder: Path
    ) -> None:
        ids = [d.id for d in DroneStore.list_drones(workspace)]
        assert "web-research" in ids

    def test_manifest_validates_as_command_read_only_drone(
        self, workspace: Path, drone: DroneStore
    ) -> None:
        assert drone.kind == "command"
        assert drone.write_policy == "read_only"
        assert drone.entrypoint["protocol"] == "json-stdio"
        assert isinstance(drone.output_contract, dict)
        assert drone.budget.timeout_seconds == 120


# ---------------------------------------------------------------------------
# Execution tests  (run through the real runner)
# ---------------------------------------------------------------------------


class TestRunWithRunner:
    def test_run_with_query_line_goal(
        self, workspace: Path, drone: DroneStore
    ) -> None:
        result = run_read_only_drone_sync(
            workspace,
            "web-research",
            drone,
            "query: World Cup matches today\nfreshness: today",
        )
        assert result["ok"] is True
        assert result["status"] == "completed"
        assert "Completed live web research" in result["summary"]

    def test_plain_goal_text_as_query(
        self, workspace: Path, drone: DroneStore
    ) -> None:
        goal = "What is the latest Python version?"
        result = run_read_only_drone_sync(workspace, "web-research", drone, goal)
        assert result["ok"] is True
        assert result["status"] == "completed"
        assert "Completed live web research" in result["summary"]

    def test_empty_goal_returns_failure(
        self, workspace: Path, drone: DroneStore
    ) -> None:
        result = run_read_only_drone_sync(workspace, "web-research", drone, "")
        assert result["ok"] is False
        assert result["status"] == "failed"
        assert "no query" in result["summary"].lower()

    def test_whitespace_only_goal_returns_failure(
        self, workspace: Path, drone: DroneStore
    ) -> None:
        result = run_read_only_drone_sync(
            workspace, "web-research", drone, "   \t  \n  "
        )
        assert result["ok"] is False
        assert result["status"] == "failed"
        assert "no query" in result["summary"].lower()


# ---------------------------------------------------------------------------
# Output shape  (run the drone directly to capture full stdout JSON)
# ---------------------------------------------------------------------------


class TestOutputShape:
    _PAYLOAD = {
        "goal": "What is the capital of France?",
        "workspace_root": "/tmp",
        "drone_id": "web-research",
        "input": {},
        "upstream": {},
    }

    def _run_drone(
        self,
        folder: Path,
        goal: str,
        monkeypatch,
        block_real_subprocess,
        fixture: dict | None = None,
    ) -> dict:
        payload = {**self._PAYLOAD, "goal": goal}
        monkeypatch.setattr(subprocess, "run", block_real_subprocess)
        monkeypatch.setenv("_AURA_MOCK_WEB_RESEARCH", "1")
        if fixture is None:
            monkeypatch.delenv("_AURA_WEB_RESEARCH_MOCK_FIXTURE", raising=False)
        else:
            monkeypatch.setenv("_AURA_WEB_RESEARCH_MOCK_FIXTURE", json.dumps(fixture))
        proc = subprocess.run(
            [sys.executable, "main.py"],
            cwd=folder,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        return json.loads(proc.stdout.strip())

    def _single_page_fixture(self, url: str, title: str, text: str) -> dict:
        return {
            "results": [{"url": url, "title": title}],
            "pages": {url: {"title": title, "text": text}},
        }

    def _assert_sourced_answer(self, data: dict, expected: str) -> None:
        assert data["ok"] is True
        assert expected in data["answer"]
        assert data["verified_facts"]
        assert data["evidence"]
        assert data["sources"]
        for fact in data["verified_facts"]:
            assert any(ev.get("supports_fact") == fact for ev in data["evidence"])
        for ev in data["evidence"]:
            assert ev.get("source_url")
            assert ev.get("excerpt")
            assert "supports_fact" in ev
        assert data["confidence"] in {"medium", "high"}

    def test_returned_cargo_shape(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        data = self._run_drone(
            web_research_folder, "What is the capital of France?",
            monkeypatch, block_real_subprocess,
        )

        required_keys = {
            "ok", "summary", "query", "answer",
            "verified_facts", "sources", "evidence", "gaps",
            "confidence", "trace", "route_used",
        }
        assert required_keys.issubset(data.keys()), (
            f"Missing keys: {required_keys - data.keys()}"
        )

        assert isinstance(data["verified_facts"], list)
        assert isinstance(data["gaps"], list)
        assert isinstance(data["trace"], list)
        assert isinstance(data["route_used"], dict)

        assert data["ok"] is True
        assert isinstance(data["answer"], str)
        assert data["confidence"] in {"low", "none"}
        assert data["query"] == "What is the capital of France?"
        assert "live_research_ready" not in data

    def test_empty_goal_direct_output(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        data = self._run_drone(
            web_research_folder, "", monkeypatch, block_real_subprocess,
        )
        assert data["ok"] is False
        assert "query is required" in data["error"]
        assert "no query" in data["summary"].lower()

    def test_generic_current_info_returns_sourced_answer(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        fixture = self._single_page_fixture(
            "https://status.example.test/current",
            "ExampleNet Status",
            "ExampleNet service status: operational as of June 27, 2026.",
        )
        data = self._run_drone(
            web_research_folder,
            "What is the current status of ExampleNet service?",
            monkeypatch,
            block_real_subprocess,
            fixture,
        )

        self._assert_sourced_answer(data, "operational")
        assert all("schedule" not in step.get("step", "") for step in data["trace"] if isinstance(step, dict))

    def test_latest_software_version_returns_sourced_answer(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        fixture = self._single_page_fixture(
            "https://downloads.example.test/python",
            "Python Downloads",
            "Latest Python release: Python 3.14.0 is the newest stable version.",
        )
        data = self._run_drone(
            web_research_folder,
            "What is the latest Python version?",
            monkeypatch,
            block_real_subprocess,
            fixture,
        )

        self._assert_sourced_answer(data, "Python 3.14.0")

    def test_release_notes_question_returns_sourced_answer(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        fixture = self._single_page_fixture(
            "https://changelog.example.test/nuitka",
            "Nuitka Changelog",
            (
                "Nuitka 2.7.12 is the latest release. "
                "Changes in Nuitka 2.7.12 include improved standalone packaging and fixes for Python 3.14."
            ),
        )
        data = self._run_drone(
            web_research_folder,
            "What changed in the latest Nuitka release?",
            monkeypatch,
            block_real_subprocess,
            fixture,
        )

        self._assert_sourced_answer(data, "improved standalone packaging")
        assert any("fixes for Python 3.14" in fact for fact in data["verified_facts"])

    def test_pricing_question_returns_sourced_answer(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        fixture = self._single_page_fixture(
            "https://pricing.example.test/openai",
            "OpenAI API Pricing",
            "GPT-4.1 pricing is $2.00 per 1M input tokens and $8.00 per 1M output tokens.",
        )
        data = self._run_drone(
            web_research_folder,
            "What is the current OpenAI API price for GPT-4.1?",
            monkeypatch,
            block_real_subprocess,
            fixture,
        )

        self._assert_sourced_answer(data, "$2.00 per 1M input tokens")
        assert "$8.00 per 1M output tokens" in data["answer"]

    def test_current_person_role_returns_sourced_answer(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        fixture = self._single_page_fixture(
            "https://leadership.example.test/microsoft",
            "Microsoft Leadership",
            "Satya Nadella is Chairman and Chief Executive Officer of Microsoft.",
        )
        data = self._run_drone(
            web_research_folder,
            "Who is the current CEO of Microsoft?",
            monkeypatch,
            block_real_subprocess,
            fixture,
        )

        self._assert_sourced_answer(data, "Satya Nadella")

    def test_mocked_world_cup_schedule_result(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        data = self._run_drone(
            web_research_folder, "What time are World Cup matches today?",
            monkeypatch, block_real_subprocess,
        )
        assert data["ok"] is True
        assert data["confidence"] != "none"
        assert "USA vs England" in data["answer"]
        assert "8:00 PM GMT" in data["answer"]
        assert any(
            "USA vs England" in fact and "8:00 PM GMT" in fact
            for fact in data["verified_facts"]
        )
        assert data["sources"]
        assert data["evidence"]
        assert any("World Cup Matches Today: USA vs ENG" in ev["excerpt"] for ev in data["evidence"])
        assert any("fifa.com" in src["url"] for src in data["sources"])

    def test_conflicting_sources_lower_confidence_and_report_gap(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        fixture = {
            "results": [
                {"url": "https://source-a.example.test/python", "title": "Python Downloads"},
                {"url": "https://source-b.example.test/python", "title": "Python Mirror"},
            ],
            "pages": {
                "https://source-a.example.test/python": {
                    "title": "Python Downloads",
                    "text": "Latest Python release: Python 3.14.0 is the newest stable version.",
                },
                "https://source-b.example.test/python": {
                    "title": "Python Mirror",
                    "text": "Latest Python release: Python 3.13.9 is the newest stable version.",
                },
            },
        }
        data = self._run_drone(
            web_research_folder,
            "What is the latest Python version?",
            monkeypatch,
            block_real_subprocess,
            fixture,
        )

        assert data["answer"]
        assert data["verified_facts"]
        assert data["evidence"]
        assert data["confidence"] == "low"
        assert any("source conflict" in gap.lower() for gap in data["gaps"])

    def test_no_clear_answer_returns_empty_answer_low_confidence_and_gap(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        fixture = self._single_page_fixture(
            "https://docs.example.test/contoso",
            "Contoso Background",
            "Contoso is a fictional company. This page has background information but no current contact answer.",
        )
        data = self._run_drone(
            web_research_folder,
            "What is the current support phone for Contoso?",
            monkeypatch,
            block_real_subprocess,
            fixture,
        )

        assert data["answer"] == ""
        assert data["verified_facts"] == []
        assert data["confidence"] == "low"
        assert any("did not clearly support" in gap for gap in data["gaps"])

    def test_all_source_fail_returns_empty_answer_and_confidence_none(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        fixture = {
            "results": [],
            "pages": {
                "https://down.example.test/source": {
                    "ok": False,
                    "title": "Down",
                    "text": "",
                    "error": "HTTP fetch error: timeout",
                }
            },
        }
        data = self._run_drone(
            web_research_folder,
            "https://down.example.test/source",
            monkeypatch,
            block_real_subprocess,
            fixture,
        )

        assert data["answer"] == ""
        assert data["verified_facts"] == []
        assert data["evidence"] == []
        assert data["confidence"] == "none"
        assert any("No useful evidence" in gap for gap in data["gaps"])

    def test_mocked_schedule_evidence_without_parse_returns_gap(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        data = self._run_drone(
            web_research_folder, "What time are matches today?",
            monkeypatch, block_real_subprocess,
        )
        assert data["ok"] is True
        assert data.get("answer", "") == ""
        assert data["confidence"] in ["none", "low"]
        assert data["sources"]
        assert data["evidence"]
        assert any("No extractable schedule match and time" in gap for gap in data["gaps"])

    def test_mocked_no_evidence_result(
        self, web_research_folder: Path, monkeypatch, block_real_subprocess
    ) -> None:
        data = self._run_drone(
            web_research_folder, "fail query",
            monkeypatch, block_real_subprocess,
        )
        assert data["ok"] is True
        assert data["confidence"] in ["none", "low"]
        assert len(data["gaps"]) > 0
        assert "HTTP fetch error" in data["gaps"][0]


class TestBrowserBackedDiscovery:
    def _load_modules(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("_AURA_MOCK_WEB_RESEARCH", raising=False)
        monkeypatch.delenv("_AURA_WEB_RESEARCH_MOCK_FIXTURE", raising=False)
        monkeypatch.delenv("_AURA_WEB_RESEARCH_DISABLE_BROWSER_DISCOVERY", raising=False)
        monkeypatch.delenv("_AURA_WEB_RESEARCH_ENABLE_DDG_HTML_FALLBACK", raising=False)
        module = _load_web_research_main()
        fetching = sys.modules["fetching"]
        pipeline = sys.modules["research_pipeline"]
        return module, fetching, pipeline

    def test_normal_question_uses_browser_discovery_as_primary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module, fetching, _pipeline = self._load_modules(monkeypatch)
        calls: list[list[str]] = []

        class FakeSession:
            def discover(self, search_queries, max_targets=8):
                calls.append(list(search_queries))
                return SimpleNamespace(
                    targets=[
                        module.SourceTarget(
                            "https://source.example.test/current",
                            "Current Source",
                            "candidate",
                        )
                    ],
                    gaps=[],
                    attempted=True,
                    blocked=False,
                    route_metadata={"browser_id": "fake"},
                )

            def close(self):
                pass

        def fallback_should_not_run(query, tags):
            raise AssertionError("DuckDuckGo HTML fallback should not run after browser discovery succeeds")

        monkeypatch.setattr(fetching, "BrowserResearchSession", FakeSession)
        monkeypatch.setattr(fetching, "_duckduckgo_html_fallback", fallback_should_not_run)

        targets = module.discover_sources(
            "What is the current status of ExampleNet?",
            ["current_info"],
        )

        assert calls
        assert [target.url for target in targets] == ["https://source.example.test/current"]
        assert targets[0].kind == "candidate"

    def test_default_source_discovery_does_not_emit_duckduckgo_html_urls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _load_web_research_main()
        monkeypatch.setenv("_AURA_MOCK_WEB_RESEARCH", "1")
        targets = module.discover_sources(
            "What is the latest Python version?",
            ["current_info", "version"],
        )

        assert targets
        assert all("html.duckduckgo.com" not in target.url for target in targets)

    def test_duckduckgo_html_fallback_not_used_after_browser_failure_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module, fetching, _pipeline = self._load_modules(monkeypatch)
        fallback_calls: list[str] = []

        class FailedSession:
            def discover(self, search_queries, max_targets=8):
                return SimpleNamespace(
                    targets=[],
                    gaps=["Browser search unavailable: test failure"],
                    attempted=True,
                    blocked=False,
                    route_metadata={"browser_id": "fake"},
                )

            def close(self):
                pass

        def fallback(query, tags):
            fallback_calls.append(query)
            return [
                module.SourceTarget(
                    "https://fallback.example.test/source",
                    "Fallback Source",
                    "candidate",
                )
            ], []

        monkeypatch.setattr(fetching, "BrowserResearchSession", FailedSession)
        monkeypatch.setattr(fetching, "_duckduckgo_html_fallback", fallback)

        discovery = module.discover_sources_with_gaps("What is the latest Python version?", ["version"])

        assert fallback_calls == []
        assert discovery.targets == []
        assert any("Browser search unavailable" in gap for gap in discovery.gaps)

    def test_duckduckgo_html_fallback_is_explicit_opt_in_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module, fetching, _pipeline = self._load_modules(monkeypatch)
        monkeypatch.setenv("_AURA_WEB_RESEARCH_DISABLE_BROWSER_DISCOVERY", "1")
        monkeypatch.setenv("_AURA_WEB_RESEARCH_ENABLE_DDG_HTML_FALLBACK", "1")
        fallback_calls: list[str] = []

        def fallback(query, tags):
            fallback_calls.append(query)
            return [
                module.SourceTarget(
                    "https://fallback-disabled.example.test/source",
                    "Fallback Source",
                    "candidate",
                )
            ], []

        monkeypatch.setattr(fetching, "_duckduckgo_html_fallback", fallback)

        discovery = module.discover_sources_with_gaps(
            "What is the latest Python version?",
            ["version"],
        )

        assert fallback_calls == ["What is the latest Python version?"]
        assert discovery.targets[0].url == "https://fallback-disabled.example.test/source"
        assert any("disabled" in gap for gap in discovery.gaps)

    def test_captcha_browser_search_gap_is_not_evidence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module, fetching, pipeline = self._load_modules(monkeypatch)

        class BlockedSession:
            @property
            def route_metadata(self):
                return {"browser_id": "fake", "browser_session_started": True}

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb):
                pass

            def discover(self, search_queries, max_targets=8):
                return SimpleNamespace(
                    targets=[],
                    gaps=[fetching.SEARCH_BLOCKED_GAP],
                    attempted=True,
                    blocked=True,
                    route_metadata=self.route_metadata,
                )

            def fetch_source(self, target, fetched_at):
                raise AssertionError("No source fetch should run when search produced no targets")

        monkeypatch.setattr(pipeline, "BrowserResearchSession", BlockedSession)
        monkeypatch.setattr(fetching, "_duckduckgo_html_fallback", lambda query, tags: ([], []))

        data = module.run_query(
            "Who is the current CEO of ExampleNet?",
            dt.datetime(2026, 6, 27, tzinfo=dt.timezone.utc),
        )

        assert fetching.SEARCH_BLOCKED_GAP in data["gaps"]
        assert data["evidence"] == []
        assert data["confidence"] == "none"

    def test_pasted_urls_are_ordinary_candidate_sources(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module, fetching, _pipeline = self._load_modules(monkeypatch)

        class FakeSession:
            def discover(self, search_queries, max_targets=8):
                return SimpleNamespace(
                    targets=[
                        module.SourceTarget(
                            "https://discovered.example.test/source",
                            "Discovered Source",
                            "candidate",
                        )
                    ],
                    gaps=[],
                    attempted=True,
                    blocked=False,
                    route_metadata={"browser_id": "fake"},
                )

            def close(self):
                pass

        monkeypatch.setattr(fetching, "BrowserResearchSession", FakeSession)
        monkeypatch.setattr(fetching, "_duckduckgo_html_fallback", lambda query, tags: ([], []))

        targets = module.discover_sources(
            "Check https://provided.example.test/page for the current status.",
            ["current_info"],
        )
        by_url = {target.url: target for target in targets}

        assert "https://discovered.example.test/source" in by_url
        assert "https://provided.example.test/page" in by_url
        assert by_url["https://provided.example.test/page"].kind == "candidate"
        assert by_url["https://discovered.example.test/source"].kind == "candidate"

    def test_run_query_reuses_one_browser_session_for_discovery_and_fetch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module, _fetching, pipeline = self._load_modules(monkeypatch)
        instances: list[object] = []

        class FakeSession:
            def __init__(self):
                self.discover_calls = 0
                self.fetch_calls: list[str] = []
                self.close_calls = 0
                instances.append(self)

            @property
            def route_metadata(self):
                return {
                    "browser_id": "fake",
                    "browser_session_started": True,
                    "browser_session_closed": self.close_calls > 0,
                }

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _tb):
                self.close()

            def discover(self, search_queries, max_targets=8):
                self.discover_calls += 1
                return SimpleNamespace(
                    targets=[
                        module.SourceTarget("https://source-a.example.test/python", "Python A", "candidate"),
                        module.SourceTarget("https://source-b.example.test/python", "Python B", "candidate"),
                    ],
                    gaps=[],
                    attempted=True,
                    blocked=False,
                    route_metadata=self.route_metadata,
                )

            def fetch_source(self, target, fetched_at):
                self.fetch_calls.append(target.url)
                text = "Latest Python release: Python 3.14.0 is the newest stable version."
                return module.FetchedSource(
                    target=target,
                    title=target.title,
                    text=text,
                    fetched_at=fetched_at,
                    ok=True,
                    excerpt=text,
                    route="browser",
                    final_url=target.url,
                )

            def close(self):
                self.close_calls += 1

        monkeypatch.setattr(pipeline, "BrowserResearchSession", FakeSession)

        data = module.run_query(
            "What is the latest Python version?",
            dt.datetime(2026, 6, 27, tzinfo=dt.timezone.utc),
        )

        assert len(instances) == 1
        session = instances[0]
        assert session.discover_calls == 1
        assert session.fetch_calls == [
            "https://source-a.example.test/python",
            "https://source-b.example.test/python",
        ]
        assert session.close_calls == 1
        assert data["route_used"]["type"] == "browser"
        assert len(data["route_used"]["browser_fetches"]) == 2


class TestScheduleExtraction:
    def test_world_cup_query_keeps_world_cup_subject(self) -> None:
        module = _load_web_research_main()
        answer, facts, evidence, gaps, confidence = module.extract_schedule_answer(
            "What time are World Cup matches today?",
            "World Cup Matches Today: USA vs ENG 8:00 PM GMT",
            dt.datetime.now(dt.timezone.utc),
        )

        assert answer == "World Cup matches today: USA vs England at 8:00 PM GMT."
        assert facts == ["USA vs England is listed at 8:00 PM GMT."]
        assert evidence
        assert confidence == "medium"

    def test_generic_schedule_query_does_not_mention_world_cup(self) -> None:
        module = _load_web_research_main()
        answer, _, _, _, confidence = module.extract_schedule_answer(
            "What time are matches today?",
            "World Cup Matches Today: USA vs ENG 8:00 PM GMT",
            dt.datetime.now(dt.timezone.utc),
        )

        assert answer == "Matches today: USA vs England at 8:00 PM GMT."
        assert "World Cup" not in answer
        assert confidence == "medium"

    def test_play_next_query_uses_next_match_subject(self) -> None:
        module = _load_web_research_main()
        answer, _, _, _, confidence = module.extract_schedule_answer(
            "Who does the USA play next?",
            "Upcoming: USA vs ENG 8:00 PM GMT",
            dt.datetime.now(dt.timezone.utc),
        )

        assert answer == "Next match: USA vs England at 8:00 PM GMT."
        assert confidence == "medium"

    def test_team_play_query_uses_team_subject(self) -> None:
        module = _load_web_research_main()
        answer, _, _, _, confidence = module.extract_schedule_answer(
            "What time does Arsenal play tomorrow?",
            "Fixture: Arsenal vs Chelsea 3:00 PM ET",
            dt.datetime.now(dt.timezone.utc),
        )

        assert answer == "Arsenal match tomorrow: Arsenal vs Chelsea at 3:00 PM ET."
        assert confidence == "medium"

    def test_no_parse_path_returns_gap_and_low_confidence(self) -> None:
        module = _load_web_research_main()
        answer, facts, evidence, gaps, confidence = module.extract_schedule_answer(
            "What time are matches today?",
            "Schedule information is available but no time appears here.",
            dt.datetime.now(dt.timezone.utc),
        )

        assert answer == ""
        assert facts == []
        assert evidence
        assert confidence in {"none", "low"}
        assert any("No extractable schedule match and time" in gap for gap in gaps)


class TestMultiSourcePipeline:
    def test_world_cup_multiple_matches_return_all_times(self) -> None:
        module = _load_web_research_main()
        target = module.SourceTarget("https://www.fifa.com/en/match-center", "FIFA Match Centre")
        fetched = [
            module.FetchedSource(
                target=target,
                title="FIFA Match Centre",
                text=(
                    "World Cup Matches Today: Panama vs England - 5:00 PM ET. "
                    "Croatia vs Ghana at 8:00 PM ET."
                ),
                fetched_at="2026-06-27T12:00:00+00:00",
                ok=True,
                excerpt="Panama vs England - 5:00 PM ET. Croatia vs Ghana at 8:00 PM ET.",
            )
        ]

        extracted = module.extract_answer(
            "What time are World Cup matches today?",
            ["world_cup", "schedule", "today"],
            fetched,
            dt.datetime.now(dt.timezone.utc),
        )

        assert extracted.answer == (
            "World Cup matches today: Panama vs England at 5:00 PM ET; "
            "Croatia vs Ghana at 8:00 PM ET."
        )
        assert len(extracted.verified_facts) == 2
        assert len(extracted.evidence) == 2
        assert extracted.confidence == "medium"

    def test_first_source_failure_second_source_success_returns_answer(self) -> None:
        module = _load_web_research_main()
        failed = module.SourceTarget("https://example.test/fail", "Failed Source")
        good = module.SourceTarget("https://example.test/schedule", "Schedule Source")
        fetched = [
            module.FetchedSource(
                target=failed,
                title="Failed Source",
                text="",
                fetched_at="2026-06-27T12:00:00+00:00",
                ok=False,
                error="HTTP fetch error: timeout",
            ),
            module.FetchedSource(
                target=good,
                title="Schedule Source",
                text="World Cup Matches Today: USA v England 8:00 PM GMT",
                fetched_at="2026-06-27T12:00:01+00:00",
                ok=True,
                excerpt="World Cup Matches Today: USA v England 8:00 PM GMT",
            ),
        ]
        query = "What time are World Cup matches today?"
        tags = ["world_cup", "schedule", "today"]

        extracted = module.extract_answer(query, tags, fetched, dt.datetime.now(dt.timezone.utc))
        result = module.build_result(query, tags, [failed, good], fetched, extracted)

        assert result["answer"] == "World Cup matches today: USA vs England at 8:00 PM GMT."
        assert result["confidence"] == "medium"
        assert any("Could not reach https://example.test/fail" in gap for gap in result["gaps"])
        assert any("another source supplied extractable evidence" in gap for gap in result["gaps"])
        assert len(result["sources"]) == 2

    def test_all_sources_fail_returns_confidence_none_and_no_answer(self) -> None:
        module = _load_web_research_main()
        targets = [
            module.SourceTarget("https://example.test/one", "One"),
            module.SourceTarget("https://example.test/two", "Two"),
        ]
        fetched = [
            module.FetchedSource(
                target=targets[0],
                title="One",
                text="",
                fetched_at="2026-06-27T12:00:00+00:00",
                ok=False,
                error="HTTP fetch error: timeout",
            ),
            module.FetchedSource(
                target=targets[1],
                title="Two",
                text="",
                fetched_at="2026-06-27T12:00:01+00:00",
                ok=False,
                error="HTTP fetch error: 500",
            ),
        ]
        query = "What time are World Cup matches today?"
        tags = ["world_cup", "schedule", "today"]

        extracted = module.extract_answer(query, tags, fetched, dt.datetime.now(dt.timezone.utc))
        result = module.build_result(query, tags, targets, fetched, extracted)

        assert result["answer"] == ""
        assert result["confidence"] == "none"
        assert result["evidence"] == []
        assert any("No useful evidence" in gap for gap in result["gaps"])

    def test_evidence_without_parse_returns_low_confidence_and_gap(self) -> None:
        module = _load_web_research_main()
        target = module.SourceTarget("https://example.test/schedule", "Schedule Source")
        fetched = [
            module.FetchedSource(
                target=target,
                title="Schedule Source",
                text="Schedule information is available, but no kickoff time appears.",
                fetched_at="2026-06-27T12:00:00+00:00",
                ok=True,
                excerpt="Schedule information is available, but no kickoff time appears.",
            )
        ]

        extracted = module.extract_answer(
            "What time are matches today?",
            ["schedule", "today"],
            fetched,
            dt.datetime.now(dt.timezone.utc),
        )

        assert extracted.answer == ""
        assert extracted.confidence == "low"
        assert extracted.evidence
        assert any("No extractable schedule match and time" in gap for gap in extracted.gaps)

    def test_generic_current_info_does_not_claim_medium_without_extraction(self) -> None:
        module = _load_web_research_main()
        target = module.SourceTarget("https://example.test/current", "Current Source")
        fetched = [
            module.FetchedSource(
                target=target,
                title="Current Source",
                text="A current page was fetched, but it does not clearly answer the question.",
                fetched_at="2026-06-27T12:00:00+00:00",
                ok=True,
                excerpt="A current page was fetched, but it does not clearly answer the question.",
            )
        ]

        extracted = module.extract_answer(
            "What is the latest Python version?",
            ["current_info"],
            fetched,
            dt.datetime.now(dt.timezone.utc),
        )

        assert extracted.answer == ""
        assert extracted.verified_facts == []
        assert extracted.confidence == "low"

    def test_retired_research_paths_are_absent(self) -> None:
        retired = [
            "run" + "_research",
            "research" + "_current_info",
            "_research" + "_mixin",
            "_research" + "_schemas",
        ]
        root = Path(__file__).resolve().parent.parent
        candidates = list((root / "aura").rglob("*.py"))
        haystack = "\n".join(path.read_text(encoding="utf-8") for path in candidates)

        for symbol in retired:
            assert symbol not in haystack
