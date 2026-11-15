"""Async SQLite storage for GGA member profiles.

All queries are parameterized (``?`` placeholders) — no f-string SQL.
Each function opens its own short-lived connection, which is fine at the
scale of a Discord community bot.
"""
from datetime import datetime, timezone as dt_timezone

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS member_profiles(
  discord_id INTEGER PRIMARY KEY,
  display_name TEXT NOT NULL,
  golfplus_username TEXT NOT NULL DEFAULT '',
  timezone TEXT NOT NULL DEFAULT '',
  available_time TEXT NOT NULL DEFAULT '',
  handicap REAL,
  preferred_tour TEXT NOT NULL DEFAULT 'Both'
    CHECK(preferred_tour IN ('ProTour', 'Accessible', 'Both')),
  updated_at TEXT NOT NULL
);
"""


async def init_db(path: str) -> None:
    """Create the tables if they do not exist yet."""
    async with aiosqlite.connect(path) as conn:
        await conn.executescript(SCHEMA)
        # Databases created before the Golf+ username field existed get
        # the column added instead of being rebuilt.
        async with conn.execute("PRAGMA table_info(member_profiles)") as cur:
            columns = {row[1] for row in await cur.fetchall()}
        if "golfplus_username" not in columns:
            await conn.execute(
                "ALTER TABLE member_profiles "
                "ADD COLUMN golfplus_username TEXT NOT NULL DEFAULT ''"
            )
        await conn.commit()


def _row_to_profile(row: aiosqlite.Row) -> dict:
    return {
        "discord_id": row["discord_id"],
        "display_name": row["display_name"],
        "golfplus_username": row["golfplus_username"],
        "timezone": row["timezone"],
        "available_time": row["available_time"],
        "handicap": row["handicap"],
        "preferred_tour": row["preferred_tour"],
        "updated_at": row["updated_at"],
    }


async def upsert_profile(
    path: str,
    *,
    discord_id: int,
    display_name: str,
    timezone: str,
    available_time: str,
    handicap,
    preferred_tour: str,
    golfplus_username: str = "",
) -> None:
    """Insert a profile, or replace the stored values if one already exists."""
    now = datetime.now(dt_timezone.utc).isoformat()
    async with aiosqlite.connect(path) as conn:
        await conn.execute(
            """INSERT INTO member_profiles
                 (discord_id, display_name, golfplus_username, timezone,
                  available_time, handicap, preferred_tour, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(discord_id) DO UPDATE SET
                 display_name = excluded.display_name,
                 golfplus_username = excluded.golfplus_username,
                 timezone = excluded.timezone,
                 available_time = excluded.available_time,
                 handicap = excluded.handicap,
                 preferred_tour = excluded.preferred_tour,
                 updated_at = excluded.updated_at""",
            (
                discord_id,
                display_name,
                golfplus_username,
                timezone,
                available_time,
                handicap,
                preferred_tour,
                now,
            ),
        )
        await conn.commit()


async def get_profile(path: str, discord_id: int) -> dict | None:
    """Return one member's profile, or None if they have not set one."""
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM member_profiles WHERE discord_id = ?",
            (discord_id,),
        ) as cur:
            row = await cur.fetchone()
    return _row_to_profile(row) if row else None


async def list_profiles(
    path: str,
    *,
    tour: str | None = None,
    timezone: str | None = None,
) -> list[dict]:
    """Return all profiles, optionally filtered by tour and/or a
    case-insensitive timezone substring. Ordered by display name."""
    query = "SELECT * FROM member_profiles"
    clauses: list[str] = []
    params: list = []
    if tour:
        clauses.append("preferred_tour = ?")
        params.append(tour)
    if timezone:
        clauses.append("timezone LIKE ?")
        params.append(f"%{timezone}%")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY display_name COLLATE NOCASE"
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(query, params) as cur:
            rows = await cur.fetchall()
    return [_row_to_profile(row) for row in rows]


async def delete_profile(path: str, discord_id: int) -> None:
    """Remove one member's profile, if one exists."""
    async with aiosqlite.connect(path) as conn:
        await conn.execute(
            "DELETE FROM member_profiles WHERE discord_id = ?",
            (discord_id,),
        )
        await conn.commit()
