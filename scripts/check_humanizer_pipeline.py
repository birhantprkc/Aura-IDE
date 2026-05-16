"""Developer-only pipeline integration checks.

Uses only stdlib and aura.humanizer. Exits 0 only when all checks pass.
"""

import ast
import sys

from aura.humanizer import HumanizerPipeline


_results: list[tuple[str, bool, str]] = []


def _pass(name: str) -> None:
    _results.append((name, True, ""))


def _fail(name: str, detail: str) -> None:
    _results.append((name, False, detail))


def _run_humanizer(code: str):
    return HumanizerPipeline().humanize_code(code, language="python")


# ---------------------------------------------------------------------------
# Check 1: markdown fenced Python is stripped
# ---------------------------------------------------------------------------
def check_markdown_strip() -> None:
    code = "```python\ndef foo():\n    return 42\n```"
    result = _run_humanizer(code)
    if result.markdown_stripped and "```" not in result.text:
        _pass("markdown_strip")
    else:
        _fail(
            "markdown_strip",
            f"markdown_stripped={result.markdown_stripped}, fence in output={'```' in result.text}",
        )


# ---------------------------------------------------------------------------
# Check 2: narration comments are removed
# ---------------------------------------------------------------------------
def check_narration_comments() -> None:
    code = (
        "# Loop through items\n"
        "def process(items):\n"
        "    # Set up counter\n"
        "    count = 0\n"
        "    # Return the result\n"
        "    return count\n"
    )
    result = _run_humanizer(code)
    if result.comments_removed > 0:
        _pass("narration_comments")
    else:
        _fail("narration_comments", f"expected >0 removed, got {result.comments_removed}")


# ---------------------------------------------------------------------------
# Check 3: transformed code remains valid Python
# ---------------------------------------------------------------------------
def check_valid_python_after_cleanup() -> None:
    code = "```python\ndef foo():\n    return 42\n```"
    result = _run_humanizer(code)
    try:
        ast.parse(result.text)
        _pass("valid_python_after_cleanup")
    except SyntaxError as exc:
        _fail("valid_python_after_cleanup", str(exc))


# ---------------------------------------------------------------------------
# Check 4: scanner catches bare except
# ---------------------------------------------------------------------------
def check_scanner_bare_except() -> None:
    code = "def foo():\n    try:\n        pass\n    except:\n        pass\n"
    result = _run_humanizer(code)
    codes = {i.code for i in (result.slop_report.issues if result.slop_report else [])}
    if "bare_except" in codes:
        _pass("scanner_bare_except")
    else:
        _fail("scanner_bare_except", f"issue codes found: {codes}")


# ---------------------------------------------------------------------------
# Check 5: scanner catches eval or exec
# ---------------------------------------------------------------------------
def check_scanner_exec_eval() -> None:
    code = "def foo():\n    eval('1+1')\n    exec('x=1')\n"
    result = _run_humanizer(code)
    codes = {i.code for i in (result.slop_report.issues if result.slop_report else [])}
    if "exec_eval_usage" in codes:
        _pass("scanner_exec_eval")
    else:
        _fail("scanner_exec_eval", f"issue codes found: {codes}")


# ---------------------------------------------------------------------------
# Check 6: scanner catches pass placeholder
# ---------------------------------------------------------------------------
def check_scanner_pass_placeholder() -> None:
    code = "def foo():\n    pass\n"
    result = _run_humanizer(code)
    codes = {i.code for i in (result.slop_report.issues if result.slop_report else [])}
    if "pass_placeholder" in codes:
        _pass("scanner_pass_placeholder")
    else:
        _fail("scanner_pass_placeholder", f"issue codes found: {codes}")


# ---------------------------------------------------------------------------
# Check 7: scanner catches NotImplementedError placeholder
# ---------------------------------------------------------------------------
def check_scanner_not_implemented() -> None:
    code = "def foo():\n    raise NotImplementedError\n"
    result = _run_humanizer(code)
    codes = {i.code for i in (result.slop_report.issues if result.slop_report else [])}
    if "not_implemented" in codes:
        _pass("scanner_not_implemented")
    else:
        _fail("scanner_not_implemented", f"issue codes found: {codes}")


# ---------------------------------------------------------------------------
# Check 8: scanner catches cross-language patterns
# ---------------------------------------------------------------------------
def check_scanner_cross_language() -> None:
    code_len = "def foo(x):\n    return x.length\n"
    code_push = "class T:\n    items = []\n    def add(self, v):\n        self.items.push(v)\n"
    result_len = _run_humanizer(code_len)
    result_push = _run_humanizer(code_push)
    codes_len = {
        i.code
        for i in (result_len.slop_report.issues if result_len.slop_report else [])
    }
    codes_push = {
        i.code
        for i in (result_push.slop_report.issues if result_push.slop_report else [])
    }

    if "js_length" not in codes_len:
        _fail("scanner_js_length", f"issue codes found: {codes_len}")
    else:
        _pass("scanner_js_length")
    if "js_push" not in codes_push:
        _fail("scanner_js_push", f"issue codes found: {codes_push}")
    else:
        _pass("scanner_js_push")


# ---------------------------------------------------------------------------
# Check 9: cleanup does not break syntax (valid Python after markdown strip)
# ---------------------------------------------------------------------------
def check_cleanup_preserves_syntax() -> None:
    code = "def foo():\n    x = 1\n    y = 2\n    return x + y\n"
    result = _run_humanizer(code)
    if result.syntax_fallback:
        _fail("cleanup_preserves_syntax", "syntax_fallback=True on clean code")
        return
    try:
        ast.parse(result.text)
        _pass("cleanup_preserves_syntax")
    except SyntaxError as exc:
        _fail("cleanup_preserves_syntax", str(exc))


def main() -> int:
    check_markdown_strip()
    check_narration_comments()
    check_valid_python_after_cleanup()
    check_scanner_bare_except()
    check_scanner_exec_eval()
    check_scanner_pass_placeholder()
    check_scanner_not_implemented()
    check_scanner_cross_language()
    check_cleanup_preserves_syntax()

    for name, ok, detail in _results:
        if ok:
            print(f"PASS {name}")
        else:
            print(f"FAIL {name} - {detail}")

    failed = sum(1 for _, ok, _ in _results if not ok)
    passed = sum(1 for _, ok, _ in _results if ok)
    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
