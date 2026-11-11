"""Catálogo SQLite: documentos originales, instantáneas de datos y ejecuciones."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime

from electoral_lab.storage import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id TEXT NOT NULL,
  url TEXT,
  fetched_at TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  path TEXT NOT NULL,
  bytes INTEGER,
  note TEXT
);
CREATE TABLE IF NOT EXISTS snapshots (
  snapshot_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  as_of TEXT NOT NULL,
  data_hash TEXT NOT NULL,
  manifest TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  snapshot_id TEXT,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  manifest TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@contextmanager
def connect():
    paths.DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(paths.CATALOG_DB)
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def record_raw(source_id: str, url: str | None, sha256: str, path: str, nbytes: int, note: str = "") -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO raw_documents(source_id,url,fetched_at,sha256,path,bytes,note) VALUES (?,?,?,?,?,?,?)",
            (source_id, url, now_iso(), sha256, path, nbytes, note),
        )


def list_raw(limit: int = 200) -> list[dict]:
    with connect() as con:
        cur = con.execute(
            "SELECT source_id,url,fetched_at,sha256,path,bytes,note FROM raw_documents ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]


def record_snapshot(snapshot_id: str, as_of: str, data_hash: str, manifest: dict) -> None:
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?,?)",
            (snapshot_id, now_iso(), as_of, data_hash, json.dumps(manifest, ensure_ascii=False)),
        )


def record_run(run_id: str, snapshot_id: str | None, kind: str, status: str, manifest: dict) -> None:
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?)",
            (run_id, now_iso(), snapshot_id, kind, status, json.dumps(manifest, ensure_ascii=False, default=str)),
        )


def list_runs() -> list[dict]:
    with connect() as con:
        cur = con.execute("SELECT run_id,created_at,snapshot_id,kind,status FROM runs ORDER BY created_at DESC")
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]
