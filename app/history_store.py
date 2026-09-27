"""Persists readings to SQLite (stdlib, no extra dependency) so the 24h
history survives a container restart. Capped at 24h regardless - old rows
are pruned on every write.
"""
import json
import os
import sqlite3
import threading
import time

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "history.db")
HISTORY_SECONDS = 24 * 60 * 60


class HistoryStore:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS readings ("
            "ts REAL PRIMARY KEY, status TEXT NOT NULL, info TEXT NOT NULL)"
        )
        self._conn.commit()
        self._prune()

    def add(self, ts: float, data: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO readings (ts, status, info) VALUES (?, ?, ?)",
                (ts, json.dumps(data.get("status", {})), json.dumps(data.get("info", {}))),
            )
            self._conn.commit()
            self._prune_locked()

    def _prune(self) -> None:
        with self._lock:
            self._prune_locked()

    def _prune_locked(self) -> None:
        cutoff = time.time() - HISTORY_SECONDS
        self._conn.execute("DELETE FROM readings WHERE ts < ?", (cutoff,))
        self._conn.commit()

    def query(self, since_epoch: float = 0.0):
        with self._lock:
            cur = self._conn.execute(
                "SELECT ts, status, info FROM readings WHERE ts >= ? ORDER BY ts",
                (since_epoch,),
            )
            rows = cur.fetchall()
        return [
            {"ts": ts, "status": json.loads(status), "info": json.loads(info)}
            for ts, status, info in rows
        ]


history_store = HistoryStore()
