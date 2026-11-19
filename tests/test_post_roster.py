"""/post-roster — public Golf+ username roster that updates itself."""
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


def register(db_path, discord_id, display_name, golfplus_username=""):
    run(
        db.upsert_team_registration(
            db_path,
            discord_id=discord_id,
            display_name=display_name,
            golfplus_username=golfplus_username,
            available_time="Evenings",
            handicap=12.0,
        )
    )


# --- database ---


def test_roster_posts_round_trip(db_path):
    run(db.init_db(db_path))
    run(
        db.add_roster_post(
            db_path, guild_id=999, channel_id=777, message_id=1000
        )
    )
    # Re-adding the same post is a no-op, not a duplicate row.
    run(
        db.add_roster_post(
            db_path, guild_id=999, channel_id=777, message_id=1000
        )
    )
    assert run(db.list_roster_posts(db_path, 999)) == [(777, 1000)]
    assert run(db.list_roster_posts(db_path, 123)) == []
    run(
        db.remove_roster_post(
            db_path, guild_id=999, channel_id=777, message_id=1000
        )
    )
    assert run(db.list_roster_posts(db_path, 999)) == []


# --- embed ---


def test_build_roster_embed_usernames_only(db_path):
    run(db.init_db(db_path))
    register(db_path, 1, "Amy", "Alumec")
    register(db_path, 2, "Ben", "BeTheNumba")
    embed = team_cog.build_roster_embed(
        run(db.list_team_registrations(db_path))
    )
    assert embed.title == "Team League roster — 2 registered"
    assert embed.description == "Alumec\nBeTheNumba"
    # No playing times, no handicaps, no display names leak in.
    assert "Evenings" not in embed.description
    assert "12" not in embed.description
    assert "Amy" not in embed.description
    assert "Ben" not in embed.description


def test_build_roster_embed_sorts_by_shown_name(db_path):
    run(db.init_db(db_path))
    register(db_path, 1, "Ben", "Zed")
    register(db_path, 2, "Amy", "apple")
    embed = team_cog.build_roster_embed(
        run(db.list_team_registrations(db_path))
    )
    assert embed.description == "apple\nZed"


def test_build_roster_embed_falls_back_to_display_name(db_path):
    run(db.init_db(db_path))
    register(db_path, 1, "Amy", "")
    embed = team_cog.build_roster_embed(
        run(db.list_team_registrations(db_path))
    )
    assert embed.description == "Amy"


def test_build_roster_embed_empty(db_path):
    run(db.init_db(db_path))
    embed = team_cog.build_roster_embed(
        run(db.list_team_registrations(db_path))
    )
    assert embed.title == "Team League roster — 0 registered"
    assert embed.description == "Nobody has registered for the team league yet."


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
        self.deleted = False
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)

    async def delete(self):
        self.deleted = True


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
    def __init__(self, perms=None):
        self.id = 123
        self.display_name = "Alumec"
        self.guild_permissions = perms or _FakePerms()


class _FakeInteraction:
    def __init__(self, perms=None, guild_id=999, client=None):
        self.user = _FakeUser(perms)
        self.response = _FakeResponse()
        self.channel = _FakeChannel()
        self.guild_id = guild_id
        self.client = client


# --- /post-roster ---


def test_post_roster_posts_for_admin_and_records(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    register(db_path, 1, "Amy", "Alumec")
    interaction = _FakeInteraction(perms=_FakePerms(manage_guild=True))
    cog = team_cog.TeamRegistrationCog(bot=None)

    async def _run():
        await team_cog.TeamRegistrationCog.post_roster.callback(
            cog, interaction
        )

    asyncio.run(_run())
    assert len(interaction.channel.sent) == 1
    posted = interaction.channel.sent[0]
    assert posted["embed"].title == "Team League roster — 1 registered"
    assert posted["embed"].description == "Alumec"
    assert run(db.list_roster_posts(db_path, 999)) == [(777, 1000)]
    assert interaction.response.sent == [
        (
            "Team roster posted in this channel — it updates itself when "
            "players register or unregister. Run /post-roster in another "
            "channel to post another copy; running it again here replaces "
            "this one.",
            {"ephemeral": True},
        )
    ]


def test_post_roster_refuses_non_admin(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    interaction = _FakeInteraction(perms=_FakePerms())
    cog = team_cog.TeamRegistrationCog(bot=None)

    async def _run():
        await team_cog.TeamRegistrationCog.post_roster.callback(
            cog, interaction
        )

    asyncio.run(_run())
    assert interaction.channel.sent == []
    assert run(db.list_roster_posts(db_path, 999)) == []
    assert interaction.response.sent == [
        ("Only admins can post the team roster.", {"ephemeral": True})
    ]


def test_post_roster_replaces_same_channel_copy(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    interaction = _FakeInteraction(perms=_FakePerms(manage_guild=True))
    bot = _FakeBot([interaction.channel])
    cog = team_cog.TeamRegistrationCog(bot=bot)

    async def _run():
        await team_cog.TeamRegistrationCog.post_roster.callback(
            cog, interaction
        )

    asyncio.run(_run())
    asyncio.run(_run())
    old_message = interaction.channel.messages[1000]
    assert old_message.deleted is True
    # Only the fresh post is recorded for this channel — no duplicate
    # live rosters in one channel.
    assert run(db.list_roster_posts(db_path, 999)) == [(777, 1001)]
    assert len(interaction.channel.sent) == 2


def test_post_roster_allows_multiple_channels(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    register(db_path, 1, "Amy", "Alumec")
    first = _FakeInteraction(perms=_FakePerms(manage_guild=True))
    second = _FakeInteraction(perms=_FakePerms(manage_guild=True))
    second.channel = _FakeChannel(channel_id=778)
    bot = _FakeBot([first.channel, second.channel])
    cog = team_cog.TeamRegistrationCog(bot=bot)

    async def _run(interaction):
        await team_cog.TeamRegistrationCog.post_roster.callback(
            cog, interaction
        )

    asyncio.run(_run(first))
    asyncio.run(_run(second))
    # Both copies are live — neither was taken down by the other.
    assert sorted(run(db.list_roster_posts(db_path, 999))) == [
        (777, 1000),
        (778, 1000),
    ]
    assert first.channel.messages[1000].deleted is False
    assert second.channel.messages[1000].deleted is False
    assert first.channel.sent[0]["embed"].description == "Alumec"
    assert second.channel.sent[0]["embed"].description == "Alumec"


# --- live updating ---


def test_refresh_edits_posted_roster_on_register(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    register(db_path, 1, "Amy", "Alumec")
    channel = _FakeChannel()
    message = asyncio.run(channel.send(embed=None))
    run(
        db.add_roster_post(
            db_path, guild_id=999, channel_id=777, message_id=message.id
        )
    )
    bot = _FakeBot([channel])
    # A new registration (via the modal, the /register-team path)
    # refreshes the posted roster in place.
    modal = team_cog.TeamModal(existing=None)
    modal.username_input._value = "BeTheNumba"
    modal.days_input._value = "Weekends"
    modal.window_input._value = "10am-1pm"
    modal.handicap_input._value = "12"
    interaction = _FakeInteraction(client=bot)
    interaction.user.id = 2
    interaction.user.display_name = "Ben"
    asyncio.run(modal.on_submit(interaction))
    assert len(message.edits) == 1
    embed = message.edits[0]["embed"]
    assert embed.title == "Team League roster — 2 registered"
    assert embed.description == "Alumec\nBeTheNumba"


def test_refresh_on_unregister_removes_player(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    register(db_path, 123, "Alumec", "Alumec")
    register(db_path, 2, "Ben", "BeTheNumba")
    channel = _FakeChannel()
    message = asyncio.run(channel.send(embed=None))
    run(
        db.add_roster_post(
            db_path, guild_id=999, channel_id=777, message_id=message.id
        )
    )
    bot = _FakeBot([channel])
    cog = team_cog.TeamRegistrationCog(bot=bot)
    interaction = _FakeInteraction(client=bot)
    asyncio.run(
        team_cog.TeamRegistrationCog.unregister_team.callback(cog, interaction)
    )
    assert run(db.get_team_registration(db_path, 123)) is None
    assert len(message.edits) == 1
    embed = message.edits[0]["embed"]
    assert embed.title == "Team League roster — 1 registered"
    assert embed.description == "BeTheNumba"


def test_refresh_drops_dead_post(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    channel = _FakeChannel()
    bot = _FakeBot([channel])
    # The recorded message no longer exists (deleted in Discord).
    run(
        db.add_roster_post(
            db_path, guild_id=999, channel_id=777, message_id=4242
        )
    )
    asyncio.run(team_cog.refresh_roster_posts(bot, 999))
    assert run(db.list_roster_posts(db_path, 999)) == []


def test_refresh_no_posts_is_noop(db_path, monkeypatch):
    monkeypatch.setattr(team_cog.config, "DB_PATH", db_path)
    run(db.init_db(db_path))
    # No posted roster and no bot: nothing to do, no error.
    asyncio.run(team_cog.refresh_roster_posts(None, 999))
    asyncio.run(team_cog.refresh_roster_posts(_FakeBot([]), 999))
