"""Instant registration: tapping Register for Team puts the member
on the roster under their Discord name, form or no form."""
import asyncio
import os
import tempfile

import pytest

from src import db
from src.cogs import team_registration as team_cog


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield os.path.join(tmp, "test.db")


# --- fakes ---


class _FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, content=None, **kwargs):
        self.sent.append((content, kwargs))

    async def send_modal(self, modal):
        self.sent.append(("modal", modal))


class _FakeMessage:
    def __init__(self, message_id, channel):
        self.id = message_id
        self.channel = channel
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class _FakeChannel:
    def __init__(self, channel_id=777):
        self.id = channel_id
        self.sent = []
        self.messages = {}
        self._next_id = 1000

    async def send(self, **kwargs):
        self.sent.append(kwargs)
        message = _FakeMessage(self._next_id, self)
        self._next_id += 1
        self.messages[message.id] = message
        return message

    async def fetch_message(self, message_id):
        if message_id not in self.messages:
            raise ValueError("message not found")
        return self.messages[message_id]


class _FakeBot:
    def __init__(self, channels):
        self.channels = {c.id: c for c in channels}

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id):
        if channel_id not in self.channels:
            raise ValueError("channel not found")
        return self.channels[channel_id]


class _FakePerms:
    def __init__(self, administrator=False, manage_guild=False):
        self.administrator = administrator
        self.manage_guild = manage_guild


class _FakeUser:
    def __init__(self, user_id=123, display_name="Alumec", perms=None):
        self.id = user_id
        self.display_name = display_name
        self.guild_permissions = perms or _FakePerms()


class _FakeInteraction:
    def __init__(self, perms=None, guild_id=999, client=None):
        self.user = _FakeUser(perms=perms)
        self.response = _FakeResponse()
        self.channel = _FakeChannel()
        self.guild_id = guild_id
        self.client = client


# --- database ---


def test_bare_insert_creates_empty_registration(db_path):
    run(db.init_db(db_path))
    assert run(
        db.insert_team_registration_bare(
            db_path, discord_id=123, display_name="Alumec"
        )
    ) is True
    reg = run(db.get_team_registration(db_path, 123))
    assert reg is not None
    assert reg["display_name"] == "Alumec"
    assert reg["golfplus_username"] == ""
    assert reg["available_time"] == ""
    assert reg["avail_days"] == ""
    assert reg["avail_start_min"] is None
    assert reg["avail_end_min"] is None
    assert reg["handicap"] is None


def test_bare_insert_never_overwrites_existing(db_path):
    run(db.init_db(db_path))
    run(
        db.upsert_team_registration(
            db_path,
            discord_id=123,
            display_name="Alumec",
            golfplus_username="Alumec",
            available_time="Weeknights 8pm–11pm ET",
            avail_days="Weeknights",
            avail_start_min=20 * 60,
            avail_end_min=23 * 60,
            handicap=12.5,
        )
    )
    assert run(
        db.insert_team_registration_bare(
            db_path, discord_id=123, display_name="Alumec"
        )
    ) is False
    reg = run(db.get_team_registration(db_path, 123))
    assert reg["golfplus_username"] == "Alumec"
    assert reg["available_time"] == "Weeknights 8pm–11pm ET"
    assert reg["handicap"] == 12.5


def test_modal_submit_fills_in_bare_registration(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    run(
        db.insert_team_registration_bare(
            db_path, discord_id=123, display_name="Alumec"
        )
    )
    modal = team_cog.TeamModal(existing=None)
    modal.username_input._value = "Alumec"
    modal.days_input._value = "Weekends"
    modal.window_input._value = "10am-1pm"
    modal.handicap_input._value = "12"
    interaction = _FakeInteraction()
    asyncio.run(modal.on_submit(interaction))
    reg = run(db.get_team_registration(db_path, 123))
    assert reg["golfplus_username"] == "Alumec"
    assert reg["available_time"] == "Weekends 10am–1pm ET"
    assert reg["handicap"] == 12.0


# --- button click ---


def test_button_click_registers_bare_and_says_so(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    interaction = _FakeInteraction()
    view = team_cog.TeamButtonView()

    async def _click():
        await view.children[0].callback(interaction)

    asyncio.run(_click())
    reg = run(db.get_team_registration(db_path, 123))
    assert reg is not None
    assert reg["display_name"] == "Alumec"
    assert reg["golfplus_username"] == ""
    assert reg["handicap"] is None
    assert len(interaction.response.sent) == 1
    content, kwargs = interaction.response.sent[0]
    assert "You're on the team roster now under your Discord name" in content
    assert "close this and you're done" in content
    assert kwargs["ephemeral"] is True
    assert isinstance(kwargs["view"], team_cog.TeamSetupView)


def test_button_click_when_registered_keeps_details(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    run(
        db.upsert_team_registration(
            db_path,
            discord_id=123,
            display_name="Alumec",
            golfplus_username="Alumec",
            available_time="Weeknights 8pm–11pm ET",
            avail_days="Weeknights",
            avail_start_min=20 * 60,
            avail_end_min=23 * 60,
            handicap=12.5,
        )
    )
    interaction = _FakeInteraction()
    view = team_cog.TeamButtonView()

    async def _click():
        await view.children[0].callback(interaction)

    asyncio.run(_click())
    reg = run(db.get_team_registration(db_path, 123))
    assert reg["golfplus_username"] == "Alumec"
    assert reg["available_time"] == "Weeknights 8pm–11pm ET"
    assert reg["handicap"] == 12.5
    content, _kwargs = interaction.response.sent[0]
    assert "You're on the team roster now" not in content
    assert "Register for the GGA Team League" in content


def test_button_click_refreshes_posted_roster(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    channel = _FakeChannel()
    message = asyncio.run(channel.send(embed=None))
    run(
        db.add_roster_post(
            db_path, guild_id=999, channel_id=777, message_id=message.id
        )
    )
    bot = _FakeBot([channel])
    interaction = _FakeInteraction(client=bot)
    interaction.channel = channel
    view = team_cog.TeamButtonView()

    async def _click():
        await view.children[0].callback(interaction)

    asyncio.run(_click())
    assert len(message.edits) == 1
    embed = message.edits[0]["embed"]
    assert embed.title == "Team League roster — 1 registered"
    # No Golf+ username yet: the bare registration shows under the
    # Discord display name.
    assert embed.description == "Alumec"


def test_button_click_without_posted_roster_is_fine(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    interaction = _FakeInteraction(client=_FakeBot([]))
    view = team_cog.TeamButtonView()

    async def _click():
        await view.children[0].callback(interaction)

    asyncio.run(_click())
    assert run(db.get_team_registration(db_path, 123)) is not None
    assert len(interaction.response.sent) == 1
