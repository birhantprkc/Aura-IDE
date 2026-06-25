from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from aura.hazard.models import HazardRecord


class HazardStore:
    def __init__(self, db_path: Path) -> None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._init_tables(conn)
            self._conn = conn
        return self._conn

    def _init_tables(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS hazards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model TEXT NOT NULL,
                status TEXT NOT NULL,
                failure_class TEXT,
                target_files TEXT,
                task_kind TEXT,
                error_signature TEXT,
                raw_errors TEXT,
                tool_call_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_hazards_model_kind
               ON hazards (model, task_kind)"""
        )

    def insert(self, record: HazardRecord) -> int:
        conn = self._get_connection()
        cur = conn.execute(
            """INSERT INTO hazards
               (model, status, failure_class, target_files, task_kind,
                error_signature, raw_errors, tool_call_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            record.to_row(),
        )
        conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def count(self) -> int:
        conn = self._get_connection()
        row = conn.execute("SELECT COUNT(*) AS cnt FROM hazards").fetchone()
        return row["cnt"]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
