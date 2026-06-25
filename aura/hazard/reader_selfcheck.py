from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

from aura.hazard.fingerprint import normalize_error
from aura.hazard.models import HazardRecord
from aura.hazard.reader import read_graduated_from_store
from aura.hazard.store import HazardStore


def _main() -> int:
    now = datetime.now(timezone.utc)

    fd, db_path_str = tempfile.mkstemp(suffix=".db")
    db_path = Path(db_path_str)
    # We must close the fd; sqlite3 will manage its own handle
    import os
    os.close(fd)

    store = HazardStore(db_path)
    try:
        # Insert three Qt-geometry rows (must cluster)
        store.insert(HazardRecord(
            model="test-model",
            status="harness_error",
            failure_class="geometry_error",
            task_kind="ui_render",
            error_signature="QWidget: Cannot set geometry of 1920x1080 on 'dice'",
            target_files=("src/ui/dice.py",),
            raw_errors=(),
            tool_call_id="tc-qt-1",
            created_at=(now - timedelta(days=5)).isoformat(timespec="seconds"),
        ))
        store.insert(HazardRecord(
            model="test-model",
            status="harness_error",
            failure_class="geometry_error",
            task_kind="ui_render",
            error_signature="QWidget: Cannot set geometry of 2560x1440 on 'roller'",
            target_files=("src/ui/roller.py",),
            raw_errors=(),
            tool_call_id="tc-qt-2",
            created_at=(now - timedelta(days=3)).isoformat(timespec="seconds"),
        ))
        store.insert(HazardRecord(
            model="test-model",
            status="harness_error",
            failure_class="geometry_error",
            task_kind="ui_render",
            error_signature="QWidget: Cannot set geometry of 1024x768 on 'panel'",
            target_files=("src/ui/panel.py",),
            raw_errors=(),
            tool_call_id="tc-qt-3",
            created_at=(now - timedelta(days=1)).isoformat(timespec="seconds"),
        ))

        # Insert three distractor rows
        store.insert(HazardRecord(
            model="test-model",
            status="harness_error",
            failure_class="harness_error",
            task_kind="import_check",
            error_signature="ImportError: No module named 'missing_lib'",
            target_files=("src/main.py",),
            raw_errors=(),
            tool_call_id="tc-import",
            created_at=(now - timedelta(days=4)).isoformat(timespec="seconds"),
        ))
        store.insert(HazardRecord(
            model="test-model",
            status="validation_failed",
            failure_class=None,
            task_kind="test_run",
            error_signature="AssertionError: Expected 5 but got 3 at /home/ci/project/test_thing.py:42",
            target_files=("tests/test_thing.py",),
            raw_errors=(),
            tool_call_id="tc-pytest",
            created_at=(now - timedelta(days=2)).isoformat(timespec="seconds"),
        ))
        store.insert(HazardRecord(
            model="test-model",
            status="harness_error",
            failure_class="harness_error",
            task_kind="lint",
            error_signature="RuntimeError: Process 12345 exited with code 1",
            target_files=(),
            raw_errors=(),
            tool_call_id="tc-runtime",
            created_at=(now - timedelta(days=6)).isoformat(timespec="seconds"),
        ))

        results = read_graduated_from_store(store, min_distinct_dispatches=3)

        if len(results) != 1:
            print(f"FAIL: expected 1 graduated hazard, got {len(results)}")
            for r in results:
                print(f"  {r.fingerprint} count={r.distinct_dispatch_count}")
            return 1

        h = results[0]

        if h.distinct_dispatch_count != 3:
            print(f"FAIL: expected distinct_dispatch_count=3, got {h.distinct_dispatch_count}")
            return 1

        if h.model != "test-model":
            print(f"FAIL: expected model='test-model', got {h.model!r}")
            return 1

        if h.failure_class != "geometry_error":
            print(f"FAIL: expected failure_class='geometry_error', got {h.failure_class!r}")
            return 1

        normalized = normalize_error(h.representative_error or "")
        if "<n>x<n>" not in normalized:
            print(f"FAIL: fingerprint does not contain '<n>x<n>': {normalized!r}")
            return 1

        low = normalized.lower()
        if "importerror" in low:
            print(f"FAIL: fingerprint contains 'importerror': {normalized!r}")
            return 1
        if "assertionerror" in low:
            print(f"FAIL: fingerprint contains 'assertionerror': {normalized!r}")
            return 1
        if "runtimeerror" in low:
            print(f"FAIL: fingerprint contains 'runtimeerror': {normalized!r}")
            return 1

        print(f"PASS: {h.fingerprint}")
        return 0

    finally:
        store.close()
        db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(_main())
