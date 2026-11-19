"""Team League registration: separate table, same form as /profile."""
import asyncio
import os
import tempfile

import discord
import pytest
from discord.ext import commands

from src import db
from src.cogs import team_registration as team_cog


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield os.path.join(tmp, "test.db")


# --- database ---


def test_team_upsert_get_round_trip(db_path):
    run(db.init_db(db_path))
    run(
        db.upsert_team_registration(
            db_path,
            discord_id=111,
            display_name="Alumec",
            golfplus_username="Alumec",
            available_time="Weeknights 8pm–11pm ET",
            avail_days="Weeknights",
            avail_start_min=20 * 60,
            avail_end_min=23 * 60,
            handicap=12.5,
        )
    )
    reg = run(db.get_team_registration(db_path, 111))
    assert reg is not None
    assert reg["display_name"] == "Alumec"
    assert reg["golfplus_username"] == "Alumec"
    assert reg["available_time"] == "Weeknights 8pm–11pm ET"
    assert reg["avail_days"] == "Weeknights"
    assert reg["avail_start_min"] == 20 * 60
    assert reg["avail_end_min"] == 23 * 60
    assert reg["handicap"] == 12.5
    assert "preferred_tour" not in reg


def test_team_upsert_updates_existing(db_path):
    run(db.init_db(db_path))
    run(
        db.upsert_team_registration(
            db_path,
            discord_id=111,
            display_name="Alumec",
            available_time="Weeknights",
            handicap=12.5,
        )
    )
    run(
        db.upsert_team_registration(
            db_path,
            discord_id=111,
            display_name="Alumec",
            available_time="Weekend mornings",
            handicap=10.0,
        )
    )
    reg = run(db.get_team_registration(db_path, 111))
    assert reg["available_time"] == "Weekend mornings"
    assert reg["handicap"] == 10.0
    assert len(run(db.list_team_registrations(db_path))) == 1


def test_team_list_returns_all_ordered(db_path):
    run(db.init_db(db_path))
    for discord_id, name, hcp in [
        (2, "Ben", 20.0),
        (1, "Amy", 8.0),
        (3, "Cal", None),
    ]:
        run(
            db.upsert_team_registration(
                db_path,
                discord_id=discord_id,
                display_name=name,
                available_time="Evenings",
                handicap=hcp,
            )
        )
    assert [
        r["display_name"] for r in run(db.list_team_registrations(db_path))
    ] == ["Amy", "Ben", "Cal"]


def test_team_delete(db_path):
    run(db.init_db(db_path))
    run(
        db.upsert_team_registration(
            db_path,
            discord_id=111,
            display_name="Alumec",
            available_time="Weeknights",
            handicap=12.5,
        )
    )
    run(db.delete_team_registration(db_path, 111))
    assert run(db.get_team_registration(db_path, 111)) is None
    # Deleting a registration that is not there is a no-op, not an error.
    run(db.delete_team_registration(db_path, 111))


def test_init_db_drops_tour_column_keeping_rows(db_path):
    # A database created while team registrations still had a tour
    # column (the schema before 2026-11-17) gets the table rebuilt
    # without it, keeping every row.
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE team_registrations(
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
        )"""
    )
    conn.execute(
        """INSERT INTO team_registrations
             (discord_id, display_name, available_time, handicap,
              preferred_tour, updated_at)
           VALUES (111, 'Alumec', 'Weeknights', 12.5, 'ProTour', 'x')"""
    )
    conn.commit()
    conn.close()
    run(db.init_db(db_path))
    reg = run(db.get_team_registration(db_path, 111))
    assert reg is not None
    assert reg["display_name"] == "Alumec"
    assert reg["handicap"] == 12.5
    assert "preferred_tour" not in reg
    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute(
        "PRAGMA table_info(team_registrations)"
    )}
    conn.close()
    assert "preferred_tour" not in columns


def test_team_get_missing_returns_none(db_path):
    run(db.init_db(db_path))
    assert run(db.get_team_registration(db_path, 999)) is None


# --- modal prefill ---


def test_team_modal_prefills_from_team_registration():
    existing = {
        "golfplus_username": "Alumec",
        "avail_days": "Weeknights",
        "avail_start_min": 20 * 60,
        "avail_end_min": 23 * 60,
        "available_time": "Weeknights 8pm–11pm ET",
        "handicap": 12.5,
    }
    modal = team_cog.TeamModal(existing=existing)
    assert len(modal.children) == 4
    values = {child.label: child.default for child in modal.children}
    assert "Timezone" not in values
    assert values["Golf+ Username"] == "Alumec"
    assert values["Days you usually play"] == "Weeknights"
    assert values["Playing window (Eastern Time)"] == "8pm-11pm"
    assert values["Golf+ Handicap"] == "12.5"


def test_team_modal_prefills_from_profile_fallback():
    # No team registration yet: the form pre-fills from the profile,
    # converting a legacy Denver window to Eastern.
    existing = {
        "golfplus_username": "Alumec",
        "timezone": "America/Denver",
        "avail_days": "Weeknights",
        "avail_start_min": 18 * 60,
        "avail_end_min": 21 * 60,
        "available_time": "Weeknights 8pm–11pm ET",
        "handicap": 12.5,
    }
    modal = team_cog.TeamModal(existing=existing)
    values = {child.label: child.default for child in modal.children}
    assert values["Playing window (Eastern Time)"] == "8pm-11pm"


# --- submit / unregister ---


class _FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, content=None, **kwargs):
        self.sent.append((content, kwargs))

    async def send_modal(self, modal):
        self.sent.append(("modal", modal))


class _FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)


class _FakePerms:
    def __init__(self, administrator=False, manage_guild=False):
        self.administrator = administrator
        self.manage_guild = manage_guild


class _FakeUser:
    def __init__(self, perms=None):
        self.id = 123
        self.display_name = "Alumec"
        self.guild_permissions = perms or _FakePerms()


class _FakeInteraction:
    def __init__(self, perms=None):
        self.user = _FakeUser(perms)
        self.response = _FakeResponse()
        self.channel = _FakeChannel()


def test_team_submit_saves_registration_not_profile(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    run(
        db.upsert_profile(
            db_path,
            discord_id=123,
            display_name="Alumec",
            golfplus_username="Alumec",
            timezone="",
            available_time="Weeknights 6pm–9pm ET",
            avail_days="Weeknights",
            avail_start_min=18 * 60,
            avail_end_min=21 * 60,
            handicap=10.0,
            preferred_tour="ProTour",
        )
    )
    modal = team_cog.TeamModal(existing=None)
    modal.username_input._value = "Alumec"
    modal.days_input._value = "Weekends"
    modal.window_input._value = "10am-1pm"
    modal.handicap_input._value = "+7"
    interaction = _FakeInteraction()
    asyncio.run(modal.on_submit(interaction))

    reg = run(db.get_team_registration(db_path, 123))
    assert reg is not None
    assert reg["available_time"] == "Weekends 10am–1pm ET"
    assert reg["avail_days"] == "Weekends"
    assert reg["handicap"] == -7.0
    assert "preferred_tour" not in reg
    # The profile is untouched by a team registration.
    profile = run(db.get_profile(db_path, 123))
    assert profile["available_time"] == "Weeknights 6pm–9pm ET"
    assert profile["handicap"] == 10.0
    assert len(interaction.response.sent) == 1
    _, kwargs = interaction.response.sent[0]
    assert kwargs["embed"].title == "You're registered for the Team League"


def test_team_submit_rejects_bad_window(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    modal = team_cog.TeamModal(existing=None)
    modal.username_input._value = "Alumec"
    modal.days_input._value = "Weekends"
    modal.window_input._value = "evenings"
    modal.handicap_input._value = "12"
    interaction = _FakeInteraction()
    asyncio.run(modal.on_submit(interaction))
    assert run(db.get_team_registration(db_path, 123)) is None
    content, kwargs = interaction.response.sent[0]
    assert "not a time window" in content
    assert kwargs["ephemeral"] is True


def test_unregister_team_removes_registration(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    run(
        db.upsert_team_registration(
            db_path,
            discord_id=123,
            display_name="Alumec",
            available_time="Weeknights",
            handicap=12.5,
        )
    )
    cog = team_cog.TeamRegistrationCog(bot=None)
    interaction = _FakeInteraction()
    asyncio.run(
        team_cog.TeamRegistrationCog.unregister_team.callback(cog, interaction)
    )
    assert run(db.get_team_registration(db_path, 123)) is None
    assert interaction.response.sent == [
        (
            "You're no longer registered for the team league. "
            "Run /register-team anytime to sign back up.",
            {"ephemeral": True},
        )
    ]
    interaction2 = _FakeInteraction()
    asyncio.run(
        team_cog.TeamRegistrationCog.unregister_team.callback(cog, interaction2)
    )
    assert "aren't registered" in interaction2.response.sent[0][0]


# --- roster + button ---


def test_team_roster_lists_with_count(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    for discord_id, name in [
        (1, "Amy"),
        (2, "Ben"),
    ]:
        run(
            db.upsert_team_registration(
                db_path,
                discord_id=discord_id,
                display_name=name,
                available_time="Evenings",
                handicap=8.0,
            )
        )
    cog = team_cog.TeamRegistrationCog(bot=None)
    interaction = _FakeInteraction(perms=_FakePerms(manage_guild=True))
    asyncio.run(
        team_cog.TeamRegistrationCog.team_roster.callback(cog, interaction)
    )
    assert len(interaction.response.sent) == 1
    _, kwargs = interaction.response.sent[0]
    assert kwargs["embed"].title == "Team League roster — 2 registered"
    assert "Amy" in kwargs["embed"].description
    assert "Ben" in kwargs["embed"].description
    assert "ProTour" not in kwargs["embed"].description
    assert "Accessible" not in kwargs["embed"].description


def test_team_roster_refuses_non_admin(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    cog = team_cog.TeamRegistrationCog(bot=None)
    interaction = _FakeInteraction(perms=_FakePerms())
    asyncio.run(
        team_cog.TeamRegistrationCog.team_roster.callback(cog, interaction)
    )
    assert interaction.response.sent == [
        ("Only crew/admins can view the team roster.", {"ephemeral": True})
    ]


def test_team_button_view_is_persistent():
    view = team_cog.TeamButtonView()
    assert view.timeout is None
    assert len(view.children) == 1
    button = view.children[0]
    assert isinstance(button, discord.ui.Button)
    assert button.custom_id == "gga_team_register_button"
    assert button.label == "Register for Team"
    assert button.style == discord.ButtonStyle.primary


def test_team_button_sends_setup_message(monkeypatch):
    async def fake_get_team_registration(db_path, discord_id):
        return None

    async def fake_get_profile(db_path, discord_id):
        return None

    async def fake_insert_bare(db_path, **kwargs):
        return False

    monkeypatch.setattr(
        team_cog.db, "get_team_registration", fake_get_team_registration
    )
    monkeypatch.setattr(team_cog.db, "get_profile", fake_get_profile)
    monkeypatch.setattr(
        team_cog.db, "insert_team_registration_bare", fake_insert_bare
    )
    interaction = _FakeInteraction()
    view = team_cog.TeamButtonView()

    async def _click():
        await view.children[0].callback(interaction)

    asyncio.run(_click())
    assert len(interaction.response.sent) == 1
    content, kwargs = interaction.response.sent[0]
    assert "Register for the GGA Team League" in content
    assert kwargs["ephemeral"] is True
    assert isinstance(kwargs["view"], team_cog.TeamSetupView)


def test_team_button_view_registers_as_persistent():
    intents = discord.Intents.default()
    intents.members = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.add_view(team_cog.TeamButtonView())
    assert len(bot.persistent_views) == 1


def test_post_team_button_posts_for_admin():
    interaction = _FakeInteraction(perms=_FakePerms(manage_guild=True))
    cog = team_cog.TeamRegistrationCog(bot=None)

    async def _run():
        await team_cog.TeamRegistrationCog.post_team_button.callback(
            cog, interaction
        )

    asyncio.run(_run())
    assert len(interaction.channel.sent) == 1
    posted = interaction.channel.sent[0]
    assert isinstance(posted["view"], team_cog.TeamButtonView)
    assert posted["embed"].title == "Register for the GGA Team League"
    assert interaction.response.sent == [
        ("Team button posted in this channel.", {"ephemeral": True})
    ]


def test_post_team_button_refuses_non_admin():
    interaction = _FakeInteraction(perms=_FakePerms())
    cog = team_cog.TeamRegistrationCog(bot=None)

    async def _run():
        await team_cog.TeamRegistrationCog.post_team_button.callback(
            cog, interaction
        )

    asyncio.run(_run())
    assert interaction.channel.sent == []
    assert interaction.response.sent == [
        ("Only crew/admins can post the team button.", {"ephemeral": True})
    ]
