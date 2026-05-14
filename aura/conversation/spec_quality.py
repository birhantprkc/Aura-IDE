"""Deterministic quality checks for Planner -> Worker dispatch specs."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SpecQualityResult:
    ok: bool
    errors: list[str]


def validate_worker_dispatch_spec(spec: str, acceptance: str) -> SpecQualityResult:
    errors: list[str] = []
    spec_text = spec or ""
    acceptance_text = acceptance or ""
    spec_lower = spec_text.lower()
    acceptance_lower = acceptance_text.lower()

    for section in (
        "Core Behavior",
        "Failure Behavior",
        "Code Shape",
        "Acceptance Checks",
    ):
        if not _has_section(spec_text, section):
            errors.append(f"missing spec section: {section}")

    if "smallest complete" not in spec_lower:
        errors.append('spec must include "smallest complete" guidance')

    if "docstring" not in spec_lower and "no module" not in spec_lower:
        errors.append('spec must include a no-ceremony/docstring constraint')

    if not _has_success_condition(acceptance_lower):
        errors.append("acceptance must include concrete success/pass conditions")

    if not _has_validation_check(acceptance_lower):
        errors.append("acceptance must include validation or a runnable check")

    if _looks_like_output_work(spec_lower) and not _has_output_content_check(acceptance_lower):
        errors.append("acceptance must include a concrete output/content check")

    return SpecQualityResult(ok=not errors, errors=errors)


def _has_section(text: str, section: str) -> bool:
    pattern = rf"(?im)^\s*(?:#{1,6}\s*)?{re.escape(section)}\s*:?\s*$"
    return re.search(pattern, text) is not None


def _has_success_condition(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "pass",
            "passes",
            "success",
            "succeeds",
            "verified",
            "verify",
            "assert",
            "expected",
            "contains",
            "equals",
            "returns",
            "exit code 0",
            "exits 0",
            "no errors",
        )
    )


def _has_validation_check(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "pytest",
            "python -m",
            "ruff",
            "mypy",
            "npm test",
            "pnpm test",
            "yarn test",
            "go test",
            "cargo test",
            "compile",
            "lint",
            "test",
            "run ",
            "command",
            "validation",
            "validate",
            "manual check",
            "verify",
        )
    )


def _looks_like_output_work(text: str) -> bool:
    output_verbs = (
        "create",
        "creates",
        "created",
        "generate",
        "generates",
        "generated",
        "render",
        "renders",
        "rendered",
        "transform",
        "transforms",
        "transformed",
        "convert",
        "converts",
        "converted",
        "export",
        "exports",
        "exported",
        "save",
        "saves",
        "saved",
        "write",
        "writes",
        "written",
    )
    output_nouns = (
        "output",
        "artifact",
        "file",
        "html",
        "markdown",
        "json",
        "csv",
        "xlsx",
        "pdf",
        "image",
        "page",
        "document",
        "report",
        "config",
        "build",
    )
    return any(verb in text for verb in output_verbs) and any(
        noun in text for noun in output_nouns
    )


def _has_output_content_check(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "content",
            "contains",
            "includes",
            "matches",
            "output",
            "file exists",
            "created file",
            "generated file",
            "rendered",
            "transformed",
            "written",
            "expected text",
            "expected content",
            "assert",
        )
    )


__all__ = ["SpecQualityResult", "validate_worker_dispatch_spec"]
