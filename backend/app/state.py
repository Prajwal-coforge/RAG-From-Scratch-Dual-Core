"""SQLite runtime state: the embedding cache and run records.

This is not a vector store. Vectors are cached only so re-ingestion does not
re-encode unchanged inputs; retrieval always reads Memgraph.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / ".local" / "state.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS embedding_cache (
    input_sha256 TEXT NOT NULL,
    model TEXT NOT NULL,
    revision TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    vector TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (input_sha256, model, revision, dimensions)
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    snapshot_id TEXT,
    generation_id TEXT,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    report TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class State:
    def __init__(self, path: Path | None = None):
        self.path = Path(os.environ.get("POLICY_RAG_STATE", path or DEFAULT_PATH))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.executescript(SCHEMA)

    def close(self) -> None:
        self._db.close()

    def cached_vectors(self, keys: Sequence[str], identity: dict) -> dict[str, list[float]]:
        found: dict[str, list[float]] = {}
        for key in keys:
            row = self._db.execute(
                "SELECT vector FROM embedding_cache WHERE input_sha256=? AND model=? AND revision=? AND dimensions=?",
                (key, identity["model"], identity["revision"], identity["dimensions"]),
            ).fetchone()
            if row:
                found[key] = json.loads(row[0])
        return found

    def store_vectors(self, vectors: dict[str, list[float]], identity: dict) -> None:
        stamp = now()
        self._db.executemany(
            "INSERT OR REPLACE INTO embedding_cache VALUES (?, ?, ?, ?, ?, ?)",
            [
                (key, identity["model"], identity["revision"], identity["dimensions"], json.dumps(vec), stamp)
                for key, vec in vectors.items()
            ],
        )
        self._db.commit()

    def start_run(self, run_id: str, kind: str, snapshot_id: str | None) -> None:
        self._db.execute(
            "INSERT INTO runs (run_id, kind, snapshot_id, status, started_at) VALUES (?, ?, ?, 'running', ?)",
            (run_id, kind, snapshot_id, now()),
        )
        self._db.commit()

    def finish_run(self, run_id: str, status: str, report: dict, generation_id: str | None = None) -> None:
        self._db.execute(
            "UPDATE runs SET status=?, finished_at=?, report=?, generation_id=? WHERE run_id=?",
            (status, now(), json.dumps(report, default=str), generation_id, run_id),
        )
        self._db.commit()

    def runs(self, limit: int = 20) -> list[dict]:
        rows = self._db.execute(
            "SELECT run_id, kind, snapshot_id, generation_id, status, started_at, finished_at FROM runs "
            "ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        keys = ("run_id", "kind", "snapshot_id", "generation_id", "status", "started_at", "finished_at")
        return [dict(zip(keys, row)) for row in rows]
