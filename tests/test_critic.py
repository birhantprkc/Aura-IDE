from aura.conversation.critic_dispatch import (
    CriticRequest,
    evaluate_deterministic_critic_request,
    parse_critic_verdict,
)
from aura.conversation.critic_verdict import CriticFinding, CriticVerdict
from aura.conversation.dispatch import WorkerDispatchRequest


def test_critic_verdict_drops_findings_without_clause_and_releases():
    verdict = CriticVerdict(
        conforms=False,
        route="worker",
        findings=[
            CriticFinding(
                clause="",
                file="a.py",
                message="Vague concern.",
                suggested_action="Patch it.",
            )
        ],
        instruction="Patch it.",
    )

    assert verdict.findings == []
    assert verdict.conforms is True
    assert verdict.route == "release"
    assert verdict.instruction == ""


def test_deterministic_critic_missing_expected_symbol_routes_worker():
    request = WorkerDispatchRequest(
        goal="Add public helper",
        files=["a.py"],
        spec="Expose run_report.",
        acceptance="run_report is available to import.",
        expected_public_symbols=["run_report"],
    )
    critic_request = CriticRequest(
        original_request=request,
        diff_text="""diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1,2 @@
+def other():
+    return None
""",
    )

    verdict = evaluate_deterministic_critic_request(critic_request)

    assert verdict is not None
    assert verdict.route == "worker"
    assert verdict.conforms is False
    assert verdict.findings[0].clause == "expected_public_symbols: run_report"


def test_parse_critic_verdict_strips_markdown_fence():
    verdict = parse_critic_verdict(
        """```json
{"conforms": true, "route": "release", "findings": []}
```"""
    )

    assert verdict.conforms is True
    assert verdict.route == "release"
