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
  avail_days TEXT NOT NULL DEFAULT '',
  avail_start_min INTEGER,
  avail_end_min INTEGER,
  handicap REAL,
  preferred_tour TEXT NOT NULL DEFAULT 'Both'
    CHECK(preferred_tour IN ('ProTour', 'Accessible', 'Both')),
  updated_at TEXT NOT NULL
);

-- Team League registrations: same shape as a profile, kept in its own
-- table so the crew can count exactly who signed up for the team
-- league. No timezone column — windows are Eastern Time from the start.
CREATE TABLE IF NOT EXISTS team_registrations(
  discord_id INTEGER PRIMARY KEY,
  display_name TEXT NOT NULL,
  golfplus_username TEXT NOT NULL DEFAULT '',
  available_time TEXT NOT NULL DEFAULT '',
  avail_days TEXT NOT NULL DEFAULT '',
  avail_start_min INTEGER,
  avail_end_min INTEGER,
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
        # Databases created before structured playing times existed get
        # the new columns added instead of being rebuilt. Old profiles
        # keep their free-text available_time; the new columns are NULL
        # for them until the member re-saves.
        for column, ddl in (
            ("avail_days", "TEXT NOT NULL DEFAULT ''"),
            ("avail_start_min", "INTEGER"),
            ("avail_end_min", "INTEGER"),
        ):
            if column not in columns:
                await conn.execute(
                    f"ALTER TABLE member_profiles ADD COLUMN {column} {ddl}"
                )
        await conn.commit()


def _row_to_profile(row: aiosqlite.Row) -> dict:
    return {
        "discord_id": row["discord_id"],
        "display_name": row["display_name"],
        "golfplus_username": row["golfplus_username"],
        "timezone": row["timezone"],
        "available_time": row["available_time"],
        "avail_days": row["avail_days"],
        "avail_start_min": row["avail_start_min"],
        "avail_end_min": row["avail_end_min"],
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
    avail_days: str = "",
    avail_start_min=None,
    avail_end_min=None,
) -> None:
    """Insert a profile, or replace the stored values if one already exists.

    ``available_time`` is the display string (the Eastern Time window
    for new saves, the member's own words for old ones).
    ``avail_days`` / ``avail_start_min`` / ``avail_end_min`` hold the
    structured window in Eastern Time; they are None/empty for profiles
    saved before structured times existed. ``timezone`` is legacy: it
    holds the zone a pre-removal profile was saved in (used once to
    convert its window to Eastern); new saves store "".
    """
    now = datetime.now(dt_timezone.utc).isoformat()
    async with aiosqlite.connect(path) as conn:
        await conn.execute(
            """INSERT INTO member_profiles
                 (discord_id, display_name, golfplus_username, timezone,
                  available_time, avail_days, avail_start_min, avail_end_min,
                  handicap, preferred_tour, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(discord_id) DO UPDATE SET
                 display_name = excluded.display_name,
                 golfplus_username = excluded.golfplus_username,
                 timezone = excluded.timezone,
                 available_time = excluded.available_time,
                 avail_days = excluded.avail_days,
                 avail_start_min = excluded.avail_start_min,
                 avail_end_min = excluded.avail_end_min,
                 handicap = excluded.handicap,
                 preferred_tour = excluded.preferred_tour,
                 updated_at = excluded.updated_at""",
            (
                discord_id,
                display_name,
                golfplus_username,
                timezone,
                available_time,
                avail_days,
                avail_start_min,
                avail_end_min,
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
) -> list[dict]:
    """Return all profiles, optionally filtered by tour.
    Ordered by display name."""
    query = "SELECT * FROM member_profiles"
    clauses: list[str] = []
    params: list = []
    if tour:
        clauses.append("preferred_tour = ?")
        params.append(tour)
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


def _row_to_team_registration(row: aiosqlite.Row) -> dict:
    return {
        "discord_id": row["discord_id"],
        "display_name": row["display_name"],
        "golfplus_username": row["golfplus_username"],
        "available_time": row["available_time"],
        "avail_days": row["avail_days"],
        "avail_start_min": row["avail_start_min"],
        "avail_end_min": row["avail_end_min"],
        "handicap": row["handicap"],
        "preferred_tour": row["preferred_tour"],
        "updated_at": row["updated_at"],
    }


async def upsert_team_registration(
    path: str,
    *,
    discord_id: int,
    display_name: str,
    available_time: str,
    handicap,
    preferred_tour: str,
    golfplus_username: str = "",
    avail_days: str = "",
    avail_start_min=None,
    avail_end_min=None,
) -> None:
    """Insert a team registration, or replace the stored values if one
    already exists. ``available_time`` is the Eastern Time display
    string; the structured window is in Eastern Time too. Registering
    for the team never touches the member's profile."""
    now = datetime.now(dt_timezone.utc).isoformat()
    async with aiosqlite.connect(path) as conn:
        await conn.execute(
            """INSERT INTO team_registrations
                 (discord_id, display_name, golfplus_username,
                  available_time, avail_days, avail_start_min, avail_end_min,
                  handicap, preferred_tour, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(discord_id) DO UPDATE SET
                 display_name = excluded.display_name,
                 golfplus_username = excluded.golfplus_username,
                 available_time = excluded.available_time,
                 avail_days = excluded.avail_days,
                 avail_start_min = excluded.avail_start_min,
                 avail_end_min = excluded.avail_end_min,
                 handicap = excluded.handicap,
                 preferred_tour = excluded.preferred_tour,
                 updated_at = excluded.updated_at""",
            (
                discord_id,
                display_name,
                golfplus_username,
                available_time,
                avail_days,
                avail_start_min,
                avail_end_min,
                handicap,
                preferred_tour,
                now,
            ),
        )
        await conn.commit()


async def get_team_registration(path: str, discord_id: int) -> dict | None:
    """Return one member's team registration, or None."""
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM team_registrations WHERE discord_id = ?",
            (discord_id,),
        ) as cur:
            row = await cur.fetchone()
    return _row_to_team_registration(row) if row else None


async def list_team_registrations(
    path: str,
    *,
    tour: str | None = None,
) -> list[dict]:
    """Return all team registrations, optionally filtered by tour.
    Ordered by display name."""
    query = "SELECT * FROM team_registrations"
    clauses: list[str] = []
    params: list = []
    if tour:
        clauses.append("preferred_tour = ?")
        params.append(tour)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY display_name COLLATE NOCASE"
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(query, params) as cur:
            rows = await cur.fetchall()
    return [_row_to_team_registration(row) for row in rows]


async def delete_team_registration(path: str, discord_id: int) -> None:
    """Remove one member's team registration, if one exists."""
    async with aiosqlite.connect(path) as conn:
        await conn.execute(
            "DELETE FROM team_registrations WHERE discord_id = ?",
            (discord_id,),
        )
        await conn.commit()
