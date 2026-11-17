"""Database round-trip: upsert / get / list / filter / delete.

Async db helpers are driven with asyncio.run() — no extra test plugins.
"""
import asyncio
import os
import tempfile

import pytest

from src import db


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield os.path.join(tmp, "test.db")


def test_upsert_get_round_trip(db_path):
    run(db.init_db(db_path))
    run(
        db.upsert_profile(
            db_path,
            discord_id=111,
            display_name="Alumec",
            golfplus_username="Alumec",
            timezone="America/Denver",
            available_time="Weeknights after 6pm MT",
            handicap=12.5,
            preferred_tour="ProTour",
        )
    )
    profile = run(db.get_profile(db_path, 111))
    assert profile is not None
    assert profile["display_name"] == "Alumec"
    assert profile["golfplus_username"] == "Alumec"
    assert profile["timezone"] == "America/Denver"
    assert profile["available_time"] == "Weeknights after 6pm MT"
    assert profile["handicap"] == 12.5
    assert profile["preferred_tour"] == "ProTour"


def test_upsert_get_structured_availability_round_trip(db_path):
    run(db.init_db(db_path))
    run(
        db.upsert_profile(
            db_path,
            discord_id=111,
            display_name="Alumec",
            golfplus_username="Alumec",
            timezone="America/Denver",
            available_time="Weeknights 8pm–11pm ET",
            avail_days="Weeknights",
            avail_start_min=18 * 60,
            avail_end_min=21 * 60,
            handicap=12.5,
            preferred_tour="ProTour",
        )
    )
    profile = run(db.get_profile(db_path, 111))
    assert profile["available_time"] == "Weeknights 8pm–11pm ET"
    assert profile["avail_days"] == "Weeknights"
    assert profile["avail_start_min"] == 18 * 60
    assert profile["avail_end_min"] == 21 * 60


def test_get_missing_profile_returns_none(db_path):
    run(db.init_db(db_path))
    assert run(db.get_profile(db_path, 999)) is None


def test_upsert_updates_existing_profile(db_path):
    run(db.init_db(db_path))
    run(
        db.upsert_profile(
            db_path,
            discord_id=111,
            display_name="Alumec",
            golfplus_username="Alumec",
            timezone="America/Denver",
            available_time="Weeknights",
            handicap=12.5,
            preferred_tour="ProTour",
        )
    )
    run(
        db.upsert_profile(
            db_path,
            discord_id=111,
            display_name="Alumec",
            golfplus_username="Alumec2",
            timezone="America/Chicago",
            available_time="Weekend mornings",
            handicap=10.0,
            preferred_tour="Both",
        )
    )
    profile = run(db.get_profile(db_path, 111))
    assert profile["golfplus_username"] == "Alumec2"
    assert profile["timezone"] == "America/Chicago"
    assert profile["available_time"] == "Weekend mornings"
    assert profile["handicap"] == 10.0
    assert profile["preferred_tour"] == "Both"
    assert len(run(db.list_profiles(db_path))) == 1


def test_list_filters(db_path):
    run(db.init_db(db_path))
    members = [
        (1, "Amy", "Evenings", 8.0, "ProTour"),
        (2, "Ben", "Mornings", 20.0, "Accessible"),
        (3, "Cal", "Weekends", None, "Both"),
    ]
    for discord_id, name, time, hcp, tour in members:
        run(
            db.upsert_profile(
                db_path,
                discord_id=discord_id,
                display_name=name,
                timezone="",
                available_time=time,
                handicap=hcp,
                preferred_tour=tour,
            )
        )
    assert len(run(db.list_profiles(db_path))) == 3
    assert [p["display_name"] for p in run(db.list_profiles(db_path, tour="ProTour"))] == [
        "Amy"
    ]


def test_init_adds_username_column_to_old_database(db_path):
    """A database created before the Golf+ username field existed gets
    the column added by init_db instead of breaking."""
    import aiosqlite

    async def _make_old_db():
        async with aiosqlite.connect(db_path) as conn:
            await conn.executescript(
                """CREATE TABLE member_profiles(
                     discord_id INTEGER PRIMARY KEY,
                     display_name TEXT NOT NULL,
                     timezone TEXT NOT NULL DEFAULT '',
                     available_time TEXT NOT NULL DEFAULT '',
                     handicap REAL,
                     preferred_tour TEXT NOT NULL DEFAULT 'Both',
                     updated_at TEXT NOT NULL
                   );"""
            )
            await conn.commit()

    run(_make_old_db())
    run(db.init_db(db_path))
    run(
        db.upsert_profile(
            db_path,
            discord_id=111,
            display_name="Alumec",
            golfplus_username="Alumec",
            timezone="America/Denver",
            available_time="Weeknights",
            handicap=12.5,
            preferred_tour="ProTour",
        )
    )
    assert run(db.get_profile(db_path, 111))["golfplus_username"] == "Alumec"


def test_init_adds_availability_columns_to_old_database(db_path):
    """A database created before structured playing times existed gets
    the new columns added by init_db, and old free-text profiles still
    load with empty structured fields."""
    import aiosqlite

    async def _make_old_db():
        async with aiosqlite.connect(db_path) as conn:
            await conn.executescript(
                """CREATE TABLE member_profiles(
                     discord_id INTEGER PRIMARY KEY,
                     display_name TEXT NOT NULL,
                     golfplus_username TEXT NOT NULL DEFAULT '',
                     timezone TEXT NOT NULL DEFAULT '',
                     available_time TEXT NOT NULL DEFAULT '',
                     handicap REAL,
                     preferred_tour TEXT NOT NULL DEFAULT 'Both',
                     updated_at TEXT NOT NULL
                   );"""
            )
            await conn.execute(
                """INSERT INTO member_profiles
                     (discord_id, display_name, timezone, available_time,
                      handicap, preferred_tour, updated_at)
                   VALUES (111, 'Alumec', 'America/Denver',
                           'Weeknights after 6pm MT', 12.5, 'ProTour', 'x')"""
            )
            await conn.commit()

    run(_make_old_db())
    run(db.init_db(db_path))
    profile = run(db.get_profile(db_path, 111))
    assert profile["available_time"] == "Weeknights after 6pm MT"
    assert profile["avail_days"] == ""
    assert profile["avail_start_min"] is None
    assert profile["avail_end_min"] is None
    run(
        db.upsert_profile(
            db_path,
            discord_id=111,
            display_name="Alumec",
            timezone="America/Denver",
            available_time="Weeknights 8pm–11pm ET",
            avail_days="Weeknights",
            avail_start_min=18 * 60,
            avail_end_min=21 * 60,
            handicap=12.5,
            preferred_tour="ProTour",
        )
    )
    profile = run(db.get_profile(db_path, 111))
    assert profile["avail_days"] == "Weeknights"
    assert profile["avail_start_min"] == 18 * 60
    assert profile["avail_end_min"] == 21 * 60


def test_delete_profile(db_path):
    run(db.init_db(db_path))
    run(
        db.upsert_profile(
            db_path,
            discord_id=111,
            display_name="Alumec",
            timezone="America/Denver",
            available_time="Weeknights",
            handicap=12.5,
            preferred_tour="ProTour",
        )
    )
    run(db.delete_profile(db_path, 111))
    assert run(db.get_profile(db_path, 111)) is None
    # Deleting a profile that is not there is a no-op, not an error.
    run(db.delete_profile(db_path, 111))
