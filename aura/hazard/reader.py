from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

from aura.hazard.fingerprint import fingerprint_fields
from aura.hazard.models import HazardRecord
from aura.hazard.store import HazardStore

__all__ = [
    "GraduatedHazard",
    "read_graduated_from_store",
    "read_graduated",
]


@dataclass(frozen=True)
class GraduatedHazard:
    fingerprint: str
    model: str
    task_kind: str | None
    failure_class: str | None
    representative_error: str | None
    distinct_dispatch_count: int
    sample_target_files: tuple[str, ...]
    first_seen: str
    last_seen: str


def read_graduated_from_store(
    store: HazardStore,
    *,
    window_days: int = 30,
    min_distinct_dispatches: int = 3,
) -> list[GraduatedHazard]:
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=window_days)
    ).isoformat(timespec="seconds")

    conn = store._get_connection()
    rows = conn.execute(
        """SELECT model, task_kind, failure_class, error_signature,
                  tool_call_id, created_at, target_files
           FROM hazards
           WHERE created_at >= ?
           ORDER BY created_at DESC""",
        (cutoff,),
    ).fetchall()

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        fp = fingerprint_fields(
            row["model"],
            row["task_kind"],
            row["failure_class"],
            row["error_signature"],
        )
        groups[fp].append(dict(row))

    result: list[GraduatedHazard] = []
    for fp, items in groups.items():
        distinct_ids = {item["tool_call_id"] for item in items}
        if len(distinct_ids) < min_distinct_dispatches:
            continue

        first_row = items[0]  # most recent due to DESC sort

        all_targets: set[str] = set()
        for item in items:
            raw = item["target_files"]
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    all_targets.update(parsed)

        created_times = [item["created_at"] for item in items]
        first_seen = min(created_times)
        last_seen = max(created_times)

        result.append(
            GraduatedHazard(
                fingerprint=fp,
                model=first_row["model"],
                task_kind=first_row["task_kind"],
                failure_class=first_row["failure_class"],
                representative_error=first_row["error_signature"],
                distinct_dispatch_count=len(distinct_ids),
                sample_target_files=tuple(sorted(all_targets)),
                first_seen=first_seen,
                last_seen=last_seen,
            )
        )

    result.sort(key=lambda h: h.distinct_dispatch_count, reverse=True)
    return result


def read_graduated(
    workspace_root: str | Path,
    *,
    window_days: int = 30,
    min_distinct_dispatches: int = 3,
) -> list[GraduatedHazard]:
    store = HazardStore(Path(workspace_root) / ".aura" / "hazards.db")
    try:
        return read_graduated_from_store(
            store,
            window_days=window_days,
            min_distinct_dispatches=min_distinct_dispatches,
        )
    finally:
        store.close()
