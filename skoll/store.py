"""SQLite-backed dedup + history. Remembers what we've already REPORTED so
each daily report only surfaces genuinely new items, and records the date we
first reported each one (so reports can say 'found on this date').

Only items that made it into a report are recorded. Anything that fell below
the threshold stays unrecorded and gets re-scored on the next run, so a repo
that starts rising later can still surface."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Item

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "skoll.db"


class Store:
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen (
                dedup_key   TEXT PRIMARY KEY,
                profile     TEXT,
                source      TEXT,
                title       TEXT,
                url         TEXT,
                first_seen  TEXT NOT NULL,
                last_score  REAL
            );
            CREATE INDEX IF NOT EXISTS idx_seen_profile ON seen(profile);
            CREATE INDEX IF NOT EXISTS idx_seen_first   ON seen(first_seen);

            -- One row per relevant item per day (reported or not): the raw
            -- material for weekly trends and star-growth tracking.
            CREATE TABLE IF NOT EXISTS observations (
                day           TEXT NOT NULL,
                profile       TEXT NOT NULL,
                dedup_key     TEXT NOT NULL,
                source        TEXT,
                title         TEXT,
                url           TEXT,
                author        TEXT,
                description   TEXT,
                repo_url      TEXT,
                created_at    TEXT,
                stars         INTEGER,
                stars_per_day REAL,
                points        INTEGER,
                comments      INTEGER,
                score         REAL,
                tags          TEXT,
                keywords      TEXT,
                reported      INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, profile, dedup_key)
            );
            CREATE INDEX IF NOT EXISTS idx_obs_profile_day ON observations(profile, day);
            """
        )
        self.conn.commit()

    def is_new(self, item: Item) -> bool:
        return not self.was_reported(item.dedup_key)

    def was_reported(self, dedup_key: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM seen WHERE dedup_key = ?", (dedup_key,)
        ).fetchone() is not None

    def mark_seen(self, item: Item, profile: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR IGNORE INTO seen
               (dedup_key, profile, source, title, url, first_seen, last_score)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (item.dedup_key, profile, item.source, item.title,
             item.url, now, item.score),
        )
        item.first_seen = datetime.now(timezone.utc)
        self.conn.commit()

    def filter_new(self, items: list[Item]) -> list[Item]:
        """Return only items never reported before. Does not record anything."""
        return [it for it in items if self.is_new(it)]

    def record_observations(self, items: list[Item], profile: str,
                            reported: set[str] | None = None,
                            day: str | None = None) -> None:
        """Snapshot today's metrics for each item. Re-running the same day
        updates the row; once reported that day, it stays reported."""
        day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        reported = reported or set()
        self.conn.executemany(
            """INSERT INTO observations
               (day, profile, dedup_key, source, title, url, author, description,
                repo_url, created_at, stars, stars_per_day, points, comments,
                score, tags, keywords, reported)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (day, profile, dedup_key) DO UPDATE SET
                 title=excluded.title, url=excluded.url,
                 description=excluded.description, repo_url=excluded.repo_url,
                 stars=excluded.stars, stars_per_day=excluded.stars_per_day,
                 points=excluded.points, comments=excluded.comments,
                 score=excluded.score, tags=excluded.tags,
                 keywords=excluded.keywords,
                 reported=MAX(reported, excluded.reported)""",
            [(day, profile, it.dedup_key, it.source, it.title, it.url, it.author,
              it.description[:500], it.repo_url,
              it.created_at.isoformat() if it.created_at else None,
              it.stars, it.stars_per_day, it.points, it.comments, it.score,
              " ".join(it.tags), ",".join(it.matched_keywords),
              1 if it.dedup_key in reported else 0) for it in items],
        )
        self.conn.commit()

    def star_baselines(self, profile: str, keys: list[str],
                       before: str) -> dict[str, tuple[str, int]]:
        """Per key: (day, stars) of the LATEST day it was reported before
        `before`; if it was never reported in a snapshot (e.g. reported before
        snapshots existed), the earliest snapshot instead."""
        out: dict[str, tuple[str, int]] = {}
        fallback: dict[str, tuple[str, int]] = {}
        for i in range(0, len(keys), 500):  # stay under SQLite's variable limit
            chunk = keys[i:i + 500]
            marks = ",".join("?" * len(chunk))
            for row in self.conn.execute(
                    f"""SELECT dedup_key, day, stars, reported FROM observations
                        WHERE profile = ? AND day < ? AND dedup_key IN ({marks})
                        ORDER BY day""", (profile, before, *chunk)):
                snap = (row["day"], row["stars"] or 0)
                if row["reported"]:
                    out[row["dedup_key"]] = snap          # later days overwrite
                fallback.setdefault(row["dedup_key"], snap)  # earliest wins
        return {k: out.get(k) or fallback[k] for k in set(out) | set(fallback)}

    def reported_on(self, profile: str, day: str) -> list[sqlite3.Row]:
        """Items that made it into a report on `day` (any earlier run that day)."""
        return self.conn.execute(
            """SELECT * FROM observations
               WHERE profile = ? AND day = ? AND reported = 1""",
            (profile, day)).fetchall()

    def observations(self, profile: str, since: str, until: str) -> list[sqlite3.Row]:
        """Rows with since <= day <= until (YYYY-MM-DD), oldest first."""
        return self.conn.execute(
            """SELECT * FROM observations
               WHERE profile = ? AND day BETWEEN ? AND ?
               ORDER BY day""", (profile, since, until)).fetchall()

    def close(self) -> None:
        self.conn.close()
