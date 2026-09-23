"""SQLite storage for collected departure records."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from gleis404.client import Departure

DEFAULT_DB_PATH = Path("data") / "gleis404.db"
"""Default database location, relative to the project root."""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS departures (
    trip_id              TEXT    NOT NULL,
    stop_id              TEXT    NOT NULL,
    scheduled_departure  TEXT    NOT NULL,
    stop_name            TEXT    NOT NULL,
    line                 TEXT    NOT NULL,
    mode                 TEXT    NOT NULL,
    headsign             TEXT,
    departure            TEXT,
    delay_seconds        INTEGER,
    real_time            INTEGER NOT NULL,
    cancelled            INTEGER NOT NULL,
    track                TEXT,
    scheduled_track      TEXT,
    collected_at         TEXT    NOT NULL,
    PRIMARY KEY (trip_id, stop_id, scheduled_departure)
);

CREATE INDEX IF NOT EXISTS idx_departures_stop_id
    ON departures (stop_id);
CREATE INDEX IF NOT EXISTS idx_departures_line
    ON departures (line);
CREATE INDEX IF NOT EXISTS idx_departures_scheduled
    ON departures (scheduled_departure);
"""


@dataclass(frozen=True, slots=True)
class WriteStats:
    """Outcome of a bulk insert operation."""

    inserted: int
    updated: int


def _to_utc(value: datetime) -> datetime:
    """Normalize a datetime to UTC, treating naive values as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _time_to_db(value: datetime | None) -> str | None:
    """Serialize a datetime for storage as an ISO-8601 UTC string."""
    return None if value is None else _to_utc(value).isoformat()


def _time_from_db(value: str | None) -> datetime | None:
    """Deserialize a stored ISO-8601 timestamp."""
    return None if value is None else datetime.fromisoformat(value)


class Database:
    """SQLite database holding historical departure records."""

    def __init__(self, path: str | Path = DEFAULT_DB_PATH) -> None:
        """Open (or create) the database and ensure the schema exists."""
        self._path = Path(path)
        if self._path.parent != Path(""):
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @property
    def path(self) -> Path:
        """Path of the database file."""
        return self._path

    @property
    def connection(self) -> sqlite3.Connection:
        """The underlying connection, for custom analytical queries."""
        return self._conn

    def insert_departures(
        self,
        departures: Sequence[Departure],
        collected_at: datetime | None = None,
    ) -> WriteStats:
        """Insert departures, refreshing rows already collected earlier."""
        if not departures:
            return WriteStats(inserted=0, updated=0)
        now = _time_to_db(collected_at or datetime.now(UTC))
        assert now is not None

        inserted = 0
        updated = 0
        cursor = self._conn.cursor()
        for dep in departures:
            exists = cursor.execute(
                "SELECT 1 FROM departures"
                " WHERE trip_id = ? AND stop_id = ?"
                " AND scheduled_departure = ?",
                (
                    dep.trip_id,
                    dep.stop_id,
                    _time_to_db(dep.scheduled_departure),
                ),
            ).fetchone()
            cursor.execute(
                """
                INSERT INTO departures (
                    trip_id, stop_id, scheduled_departure, stop_name,
                    line, mode, headsign, departure, delay_seconds,
                    real_time, cancelled, track, scheduled_track,
                    collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (trip_id, stop_id, scheduled_departure)
                DO UPDATE SET
                    stop_name       = excluded.stop_name,
                    line            = excluded.line,
                    mode            = excluded.mode,
                    headsign        = excluded.headsign,
                    departure       = excluded.departure,
                    delay_seconds   = excluded.delay_seconds,
                    real_time       = excluded.real_time,
                    cancelled       = excluded.cancelled,
                    track           = excluded.track,
                    scheduled_track = excluded.scheduled_track,
                    collected_at    = excluded.collected_at
                """,
                (
                    dep.trip_id,
                    dep.stop_id,
                    _time_to_db(dep.scheduled_departure),
                    dep.stop_name,
                    dep.line,
                    dep.mode,
                    dep.headsign,
                    _time_to_db(dep.departure),
                    dep.delay_seconds,
                    int(dep.real_time),
                    int(dep.cancelled),
                    dep.track,
                    dep.scheduled_track,
                    now,
                ),
            )
            if exists is None:
                inserted += 1
            else:
                updated += 1
        self._conn.commit()
        return WriteStats(inserted=inserted, updated=updated)

    def query_departures(
        self,
        stop_id: str | None = None,
        line: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int | None = None,
    ) -> list[Departure]:
        """Fetch stored departures, newest first."""
        clauses: list[str] = []
        params: list[object] = []
        if stop_id is not None:
            clauses.append("stop_id = ?")
            params.append(stop_id)
        if line is not None:
            clauses.append("line = ?")
            params.append(line)
        if since is not None:
            clauses.append("scheduled_departure >= ?")
            params.append(_time_to_db(since))
        if until is not None:
            clauses.append("scheduled_departure < ?")
            params.append(_time_to_db(until))
        sql = "SELECT * FROM departures"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY scheduled_departure DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_departure(row) for row in rows]

    def count_departures(self) -> int:
        """Return the total number of stored departure records."""
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM departures"
        ).fetchone()
        assert row is not None
        return int(row["n"])

    @staticmethod
    def _row_to_departure(row: sqlite3.Row) -> Departure:
        """Convert a database row back into a Departure."""
        return Departure(
            trip_id=row["trip_id"],
            stop_id=row["stop_id"],
            stop_name=row["stop_name"],
            line=row["line"],
            mode=row["mode"],
            headsign=row["headsign"],
            scheduled_departure=datetime.fromisoformat(
                row["scheduled_departure"]
            ),
            departure=_time_from_db(row["departure"]),
            delay_seconds=row["delay_seconds"],
            real_time=bool(row["real_time"]),
            cancelled=bool(row["cancelled"]),
            track=row["track"],
            scheduled_track=row["scheduled_track"],
        )

    def close(self) -> None:
        """Commit pending changes and close the connection."""
        self._conn.commit()
        self._conn.close()

    def __enter__(self) -> Self:
        """Enter a context manager; returns this database."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Exit the context manager, closing the connection."""
        self.close()
