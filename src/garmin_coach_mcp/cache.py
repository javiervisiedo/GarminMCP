"""SQLite-backed local TTL cache for Garmin Connect API responses."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class TTLCache:
    """Thread-safe SQLite-backed local Time-To-Live (TTL) cache.

    Uses parameterized SQL queries exclusively and restricts cache directory
    permissions to 0o700 (and database file to 0o600).
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        default_ttl: int = 900,
    ) -> None:
        if default_ttl == 900 and "GARMIN_CACHE_TTL" in os.environ:
            try:
                default_ttl = int(os.environ["GARMIN_CACHE_TTL"])
            except ValueError:
                default_ttl = 900

        self.default_ttl: int = default_ttl
        self._lock = threading.RLock()

        if db_path is None:
            cache_dir_str = os.environ.get("GARMIN_CACHE_DIR", "~/.cache/garmin-coach-mcp")
            cache_dir = Path(cache_dir_str).expanduser()
            self.db_path: str | Path = cache_dir / "cache.db"
        elif str(db_path) == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = Path(db_path).expanduser()

        if isinstance(self.db_path, Path):
            parent_dir = self.db_path.parent
            try:
                parent_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.chmod(parent_dir, 0o700)
                self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
                if self.db_path.exists():
                    os.chmod(self.db_path, 0o600)
            except (OSError, sqlite3.OperationalError):
                if db_path is not None:
                    raise
                self.db_path = ":memory:"
                self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)

        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cache_expires_at
                ON cache_entries (expires_at)
                """
            )

    def get(self, key: str) -> Any | None:
        """Retrieve a deserialized JSON payload if present and not expired.

        Deletes the entry and returns None if the entry has expired.
        """
        now = time.time()
        with self._lock:
            cursor = self._conn.execute(
                "SELECT value, expires_at FROM cache_entries WHERE key = ?",
                (key,),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            raw_value, expires_at = row
            if expires_at <= now:
                with self._conn:
                    self._conn.execute(
                        "DELETE FROM cache_entries WHERE key = ?",
                        (key,),
                    )
                return None

            try:
                return json.loads(raw_value)
            except (json.JSONDecodeError, TypeError):
                return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Serialize value to JSON and store with an expiration timestamp."""
        effective_ttl = self.default_ttl if ttl is None else ttl
        now = time.time()
        expires_at = now + effective_ttl
        serialized = json.dumps(value, default=str)

        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO cache_entries (key, value, expires_at, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    expires_at = excluded.expires_at,
                    created_at = excluded.created_at
                """,
                (key, serialized, expires_at, now),
            )

    def invalidate(self, key_prefix: str | None = None) -> None:
        """Invalidate cache entries matching key_prefix, or clear entire cache if None."""
        with self._lock, self._conn:
            if key_prefix is None:
                self._conn.execute("DELETE FROM cache_entries")
            else:
                self._conn.execute(
                    "DELETE FROM cache_entries WHERE substr(key, 1, ?) = ?",
                    (len(key_prefix), key_prefix),
                )

    def clear_expired(self) -> int:
        """Remove all expired rows from the cache and return the count of deleted rows."""
        now = time.time()
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "DELETE FROM cache_entries WHERE expires_at <= ?",
                (now,),
            )
            return int(cursor.rowcount if cursor.rowcount is not None and cursor.rowcount >= 0 else 0)

    @staticmethod
    def make_key(namespace: str, *args: Any, **kwargs: Any) -> str:
        """Build a deterministic cache key from a namespace, positional args, and keyword args."""
        parts: list[str] = [str(namespace)]
        for arg in args:
            if isinstance(arg, (dict, list, tuple)):
                parts.append(json.dumps(arg, sort_keys=True, default=str))
            else:
                parts.append(str(arg))
        for k, v in sorted(kwargs.items()):
            if isinstance(v, (dict, list, tuple)):
                val_str = json.dumps(v, sort_keys=True, default=str)
            else:
                val_str = str(v)
            parts.append(f"{k}={val_str}")
        return ":".join(parts)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()
