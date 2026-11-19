"""Crew/admin setup-for-others: /setup-profile-for, /register-team-for,
/unregister-team-for.

An admin fills in the same form for another member; the save lands on
the target's row, never the admin's. Non-admins are refused, bots are
refused, and the team unregister gives the admin a way to undo a
mistaken registration.
"""
import asyncio
import os
import tempfile

import pytest

from src import db
from src.cogs import profiles as profiles_cog
from src.cogs import team_registration as team_cog


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

    async def send_modal(self, modal):
        self.sent.append(("modal", modal))


class _FakePerms:
    def __init__(self, administrator=False, manage_guild=False):
        self.administrator = administrator
        self.manage_guild = manage_guild


class _FakeUser:
    def __init__(self, perms=None):
        self.id = 123
        self.display_name = "Alumec"
        self.guild_permissions = perms or _FakePerms()


class _FakeMember:
    def __init__(self, bot=False):
        self.id = 999
        self.display_name = "Ben"
        self.bot = bot


class _FakeInteraction:
    def __init__(self, perms=None):
        self.user = _FakeUser(perms)
        self.response = _FakeResponse()


def _admin_interaction():
    return _FakeInteraction(perms=_FakePerms(manage_guild=True))


# --- /setup-profile-for ---


def test_profile_modal_submit_saves_under_target(db_path, monkeypatch):
    monkeypatch.setattr(profiles_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    modal = profiles_cog.ProfileModal(
        tour="ProTour", existing=None, target=_FakeMember()
    )
    modal.username_input._value = "BenG"
    modal.days_input._value = "Weekends"
    modal.window_input._value = "10am-1pm"
    modal.handicap_input._value = "12"
    asyncio.run(modal.on_submit(_FakeInteraction()))

    profile = run(db.get_profile(db_path, 999))
    assert profile is not None
    assert profile["display_name"] == "Ben"
    assert profile["golfplus_username"] == "BenG"
    assert profile["available_time"] == "Weekends 10am–1pm ET"
    assert profile["handicap"] == 12.0
    assert profile["preferred_tour"] == "ProTour"
    # Nothing is saved under the admin who filled the form in.
    assert run(db.get_profile(db_path, 123)) is None


def test_profile_modal_submit_for_target_names_them(db_path, monkeypatch):
    monkeypatch.setattr(profiles_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    modal = profiles_cog.ProfileModal(
        tour="Accessible", existing=None, target=_FakeMember()
    )
    modal.username_input._value = ""
    modal.days_input._value = "Weeknights"
    modal.window_input._value = "6pm-9pm"
    modal.handicap_input._value = "+7"
    interaction = _FakeInteraction()
    asyncio.run(modal.on_submit(interaction))
    assert run(db.get_profile(db_path, 999))["handicap"] == -7.0
    _, kwargs = interaction.response.sent[0]
    assert kwargs["embed"].title == "Ben's GGA profile is saved"
    assert "Set by an admin" in kwargs["embed"].description


def test_setup_profile_for_refuses_non_admin():
    cog = profiles_cog.ProfilesCog(bot=None)
    interaction = _FakeInteraction()
    asyncio.run(
        profiles_cog.ProfilesCog.setup_profile_for.callback(
            cog, interaction, _FakeMember()
        )
    )
    assert interaction.response.sent == [
        (
            "Only crew/admins can set up profiles for other members.",
            {"ephemeral": True},
        )
    ]


def test_setup_profile_for_refuses_bot():
    cog = profiles_cog.ProfilesCog(bot=None)
    interaction = _admin_interaction()
    asyncio.run(
        profiles_cog.ProfilesCog.setup_profile_for.callback(
            cog, interaction, _FakeMember(bot=True)
        )
    )
    assert interaction.response.sent == [
        ("Bots don't need a GGA profile.", {"ephemeral": True})
    ]


def test_setup_profile_for_sends_setup_for_admin(monkeypatch):
    async def fake_get_profile(db_path, discord_id):
        assert discord_id == 999  # the target, not the admin
        return {"preferred_tour": "Both"}

    monkeypatch.setattr(profiles_cog.db, "get_profile", fake_get_profile)
    cog = profiles_cog.ProfilesCog(bot=None)
    interaction = _admin_interaction()
    member = _FakeMember()
    asyncio.run(
        profiles_cog.ProfilesCog.setup_profile_for.callback(
            cog, interaction, member
        )
    )
    assert len(interaction.response.sent) == 1
    content, kwargs = interaction.response.sent[0]
    assert "Ben" in content
    assert "not yours" in content
    assert kwargs["ephemeral"] is True
    view = kwargs["view"]
    assert isinstance(view, profiles_cog.ProfileSetupView)
    assert view.target is member
    assert view.tour == "Both"


# --- /register-team-for ---


def test_team_modal_submit_saves_under_target(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    modal = team_cog.TeamModal(existing=None, target=_FakeMember())
    modal.username_input._value = "BenG"
    modal.days_input._value = "Weekends"
    modal.window_input._value = "10am-1pm"
    modal.handicap_input._value = "12"
    asyncio.run(modal.on_submit(_FakeInteraction()))

    reg = run(db.get_team_registration(db_path, 999))
    assert reg is not None
    assert reg["display_name"] == "Ben"
    assert reg["available_time"] == "Weekends 10am–1pm ET"
    assert reg["handicap"] == 12.0
    assert run(db.get_team_registration(db_path, 123)) is None


def test_team_modal_submit_for_target_names_them(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    modal = team_cog.TeamModal(existing=None, target=_FakeMember())
    modal.username_input._value = ""
    modal.days_input._value = "Weeknights"
    modal.window_input._value = "6pm-9pm"
    modal.handicap_input._value = "8"
    interaction = _FakeInteraction()
    asyncio.run(modal.on_submit(interaction))
    _, kwargs = interaction.response.sent[0]
    assert kwargs["embed"].title == "Ben is registered for the Team League"
    assert "Set by an admin" in kwargs["embed"].description


def test_register_team_for_refuses_non_admin():
    cog = team_cog.TeamRegistrationCog(bot=None)
    interaction = _FakeInteraction()
    asyncio.run(
        team_cog.TeamRegistrationCog.register_team_for.callback(
            cog, interaction, _FakeMember()
        )
    )
    assert interaction.response.sent == [
        (
            "Only crew/admins can register other members for the team league.",
            {"ephemeral": True},
        )
    ]


def test_register_team_for_refuses_bot():
    cog = team_cog.TeamRegistrationCog(bot=None)
    interaction = _admin_interaction()
    asyncio.run(
        team_cog.TeamRegistrationCog.register_team_for.callback(
            cog, interaction, _FakeMember(bot=True)
        )
    )
    assert interaction.response.sent == [
        ("Bots don't play in the Team League.", {"ephemeral": True})
    ]


def test_register_team_for_sends_setup_for_admin(monkeypatch):
    async def fake_get_team_registration(db_path, discord_id):
        assert discord_id == 999  # the target, not the admin
        return None

    async def fake_get_profile(db_path, discord_id):
        return {
            "golfplus_username": "BenG",
            "avail_days": "Weekends",
            "avail_start_min": 10 * 60,
            "avail_end_min": 13 * 60,
            "available_time": "Weekends 10am–1pm ET",
            "handicap": 12.0,
        }

    monkeypatch.setattr(
        team_cog.db, "get_team_registration", fake_get_team_registration
    )
    monkeypatch.setattr(team_cog.db, "get_profile", fake_get_profile)
    cog = team_cog.TeamRegistrationCog(bot=None)
    interaction = _admin_interaction()
    member = _FakeMember()
    asyncio.run(
        team_cog.TeamRegistrationCog.register_team_for.callback(
            cog, interaction, member
        )
    )
    assert len(interaction.response.sent) == 1
    content, kwargs = interaction.response.sent[0]
    assert "Ben" in content
    assert "not yours" in content
    assert kwargs["ephemeral"] is True
    view = kwargs["view"]
    assert isinstance(view, team_cog.TeamSetupView)
    assert view.target is member


# --- /unregister-team-for ---


def test_unregister_team_for_removes_registration(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    run(
        db.upsert_team_registration(
            db_path,
            discord_id=999,
            display_name="Ben",
            available_time="Weeknights",
            handicap=12.5,
        )
    )
    cog = team_cog.TeamRegistrationCog(bot=None)
    interaction = _admin_interaction()
    asyncio.run(
        team_cog.TeamRegistrationCog.unregister_team_for.callback(
            cog, interaction, _FakeMember()
        )
    )
    assert run(db.get_team_registration(db_path, 999)) is None
    assert interaction.response.sent == [
        (
            "Ben is no longer registered for the team league.",
            {"ephemeral": True},
        )
    ]
    interaction2 = _admin_interaction()
    asyncio.run(
        team_cog.TeamRegistrationCog.unregister_team_for.callback(
            cog, interaction2, _FakeMember()
        )
    )
    assert "isn't registered" in interaction2.response.sent[0][0]


def test_unregister_team_for_refuses_non_admin():
    cog = team_cog.TeamRegistrationCog(bot=None)
    interaction = _FakeInteraction()
    asyncio.run(
        team_cog.TeamRegistrationCog.unregister_team_for.callback(
            cog, interaction, _FakeMember()
        )
    )
    assert interaction.response.sent == [
        (
            "Only crew/admins can pull other members out of the team league.",
            {"ephemeral": True},
        )
    ]
