"""/roster — crew/admin list of saved member profiles, with Show more."""
import asyncio
import os
import tempfile

import pytest

from src import db
from src.cogs import roster as roster_cog
from src.expandable_list import ExpandableListView


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield os.path.join(tmp, "test.db")


class _FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, content=None, **kwargs):
        self.sent.append((content, kwargs))


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


def _add_profile(db_path, discord_id, name, tour="ProTour"):
    run(
        db.upsert_profile(
            db_path,
            discord_id=discord_id,
            display_name=name,
            golfplus_username=name,
            timezone="",
            available_time="Evenings",
            avail_days="Weeknights",
            avail_start_min=18 * 60,
            avail_end_min=21 * 60,
            handicap=8.0,
            preferred_tour=tour,
        )
    )


def _run_roster(db_path, interaction, **kwargs):
    cog = roster_cog.RosterCog(bot=None)
    asyncio.run(roster_cog.RosterCog.roster.callback(cog, interaction, **kwargs))


def test_roster_refuses_non_admin(db_path, monkeypatch):
    monkeypatch.setattr(roster_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    interaction = _FakeInteraction(perms=_FakePerms())
    _run_roster(db_path, interaction)
    assert interaction.response.sent == [
        ("Only crew/admins can view the roster.", {"ephemeral": True})
    ]


def test_roster_empty(db_path, monkeypatch):
    monkeypatch.setattr(roster_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    interaction = _FakeInteraction(perms=_FakePerms(manage_guild=True))
    _run_roster(db_path, interaction)
    assert interaction.response.sent == [
        ("No saved profiles match those filters yet.", {"ephemeral": True})
    ]


def test_roster_short_list_has_no_button(db_path, monkeypatch):
    monkeypatch.setattr(roster_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    _add_profile(db_path, 1, "Amy")
    _add_profile(db_path, 2, "Ben")
    interaction = _FakeInteraction(perms=_FakePerms(manage_guild=True))
    _run_roster(db_path, interaction)
    _, kwargs = interaction.response.sent[0]
    assert kwargs["ephemeral"] is True
    assert kwargs["embed"].title == "GGA member roster (2 saved)"
    assert "Amy" in kwargs["embed"].description
    assert "Ben" in kwargs["embed"].description
    assert "ProTour" in kwargs["embed"].description
    assert kwargs["view"] is None
    assert kwargs["embed"].footer.text is None


def test_roster_over_20_has_show_more_button(db_path, monkeypatch):
    monkeypatch.setattr(roster_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    for discord_id in range(1, 26):
        _add_profile(db_path, discord_id, f"Player {discord_id:02d}")
    interaction = _FakeInteraction(perms=_FakePerms(manage_guild=True))
    _run_roster(db_path, interaction)
    _, kwargs = interaction.response.sent[0]
    assert kwargs["embed"].title == "GGA member roster (25 saved)"
    assert len(kwargs["embed"].description.splitlines()) == 20
    assert "Player 25" not in kwargs["embed"].description
    assert kwargs["embed"].footer.text == (
        "Showing the first 20 of 25 — narrow it down with the tour filter."
    )
    view = kwargs["view"]
    assert isinstance(view, ExpandableListView)
    assert view.toggle.label == "Show more (5 more)"


def test_roster_tour_filter_narrows_list(db_path, monkeypatch):
    monkeypatch.setattr(roster_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    for discord_id in range(1, 23):
        _add_profile(db_path, discord_id, f"Player {discord_id:02d}", tour="Accessible")
    _add_profile(db_path, 100, "Amy", tour="ProTour")
    _add_profile(db_path, 101, "Ben", tour="ProTour")
    _add_profile(db_path, 102, "Cal", tour="ProTour")
    interaction = _FakeInteraction(perms=_FakePerms(manage_guild=True))
    _run_roster(db_path, interaction, tour="ProTour")
    _, kwargs = interaction.response.sent[0]
    assert kwargs["embed"].title == "GGA member roster (3 saved)"
    assert "Amy" in kwargs["embed"].description
    assert "Player 01" not in kwargs["embed"].description
    assert kwargs["view"] is None
