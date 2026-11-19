"""Cogs load onto a Bot instance without connecting to Discord.

No login, no network — add_cog only, then check the slash commands
registered on the command tree.
"""
import asyncio

import discord
from discord.ext import commands

from src.cogs import profiles as profiles_cog
from src.cogs import roster as roster_cog
from src.cogs import team_registration as team_cog
from src.cogs import welcome as welcome_cog


def make_bot():
    intents = discord.Intents.default()
    intents.members = True
    return commands.Bot(command_prefix="!", intents=intents)


def test_all_cogs_load_and_register_commands():
    bot = make_bot()
    import asyncio

    async def _load():
        await bot.add_cog(profiles_cog.ProfilesCog(bot))
        await bot.add_cog(roster_cog.RosterCog(bot))
        await bot.add_cog(team_cog.TeamRegistrationCog(bot))
        await bot.add_cog(welcome_cog.WelcomeCog(bot))

    asyncio.run(_load())
    names = {cmd.name for cmd in bot.tree.get_commands()}
    assert names == {
        "profile",
        "roster",
        "post-profile-button",
        "setup-profile-for",
        "register-team",
        "unregister-team",
        "team-roster",
        "post-team-button",
        "post-roster",
        "register-team-for",
        "unregister-team-for",
    }


def test_profile_modal_prefills_existing_values():
    existing = {
        "golfplus_username": "Alumec",
        "timezone": "America/Denver",
        "avail_days": "Weeknights",
        "avail_start_min": 18 * 60,
        "avail_end_min": 21 * 60,
        "available_time": "Weeknights 8pm–11pm ET",
        "handicap": 12.5,
        "preferred_tour": "Accessible",
    }
    modal = profiles_cog.ProfileModal(tour="Accessible", existing=existing)
    assert len(modal.children) == 4
    values = {child.label: child.default for child in modal.children}
    assert "Timezone" not in values
    assert values["Golf+ Username"] == "Alumec"
    assert values["Days you usually play"] == "Weeknights"
    # Saved in Denver time (6pm-9pm MST) — prefilled converted to Eastern.
    assert values["Playing window (Eastern Time)"] == "8pm-11pm"
    assert values["Golf+ Handicap"] == "12.5"


def test_profile_modal_prefills_eastern_window_as_is():
    # No stored timezone: the window is already Eastern Time.
    existing = {
        "golfplus_username": "Alumec",
        "timezone": "",
        "avail_days": "Weeknights",
        "avail_start_min": 18 * 60,
        "avail_end_min": 21 * 60,
        "available_time": "Weeknights 6pm–9pm ET",
        "handicap": 12.5,
        "preferred_tour": "Accessible",
    }
    modal = profiles_cog.ProfileModal(tour="Accessible", existing=existing)
    values = {child.label: child.default for child in modal.children}
    assert values["Playing window (Eastern Time)"] == "6pm-9pm"


def test_profile_modal_leaves_days_and_window_blank_for_legacy_profile():
    # Saved before structured times: the free-text entry cannot be
    # split into days + a window, so the new fields start empty.
    existing = {
        "golfplus_username": "Alumec",
        "available_time": "Weeknights after 6pm MT",
        "avail_days": "",
        "avail_start_min": None,
        "avail_end_min": None,
        "handicap": 12.5,
        "preferred_tour": "Accessible",
    }
    modal = profiles_cog.ProfileModal(tour="Accessible", existing=existing)
    values = {child.label: child.default for child in modal.children}
    assert values["Days you usually play"] == ""
    assert values["Playing window (Eastern Time)"] == ""


def test_profile_modal_prefills_plus_handicap_with_plus_sign():
    modal = profiles_cog.ProfileModal(tour="ProTour", existing={"handicap": -7.0})
    values = {child.label: child.default for child in modal.children}
    assert values["Golf+ Handicap"] == "+7"


def test_profile_setup_view_preselects_current_tour():
    view = profiles_cog.ProfileSetupView(existing={"preferred_tour": "Both"})
    assert view.tour == "Both"
    select = next(
        child for child in view.children if isinstance(child, profiles_cog.TourSelect)
    )
    defaults = [opt.label for opt in select.options if opt.default]
    assert defaults == ["Both"]


def test_profile_setup_view_without_existing_profile():
    view = profiles_cog.ProfileSetupView(existing=None)
    assert view.tour is None


def test_profile_button_view_is_persistent():
    # timeout=None + a fixed custom_id is what keeps the button working
    # across bot restarts — the whole point of the persistent button.
    view = profiles_cog.ProfileButtonView()
    assert view.timeout is None
    assert len(view.children) == 1
    button = view.children[0]
    assert isinstance(button, discord.ui.Button)
    assert button.custom_id == "gga_profile_setup_button"
    assert button.label == "Set Up Your Profile"
    assert button.style == discord.ButtonStyle.primary


class _FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, content=None, **kwargs):
        self.sent.append((content, kwargs))


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
        self.guild_permissions = perms or _FakePerms()


class _FakeInteraction:
    def __init__(self, perms=None):
        self.user = _FakeUser(perms)
        self.response = _FakeResponse()
        self.channel = _FakeChannel()


def test_profile_button_sends_setup_message(monkeypatch):
    async def fake_get_profile(db_path, discord_id):
        return None

    monkeypatch.setattr(profiles_cog.db, "get_profile", fake_get_profile)
    interaction = _FakeInteraction()
    view = profiles_cog.ProfileButtonView()

    async def _click():
        await view.children[0].callback(interaction)

    asyncio.run(_click())
    assert len(interaction.response.sent) == 1
    content, kwargs = interaction.response.sent[0]
    assert "Set your GGA profile" in content
    assert kwargs["ephemeral"] is True
    assert isinstance(kwargs["view"], profiles_cog.ProfileSetupView)


def test_profile_button_view_registers_as_persistent():
    # Mirrors what setup_hook does: the view must land in
    # persistent_views or the button dies on the next restart.
    bot = make_bot()
    bot.add_view(profiles_cog.ProfileButtonView())
    assert len(bot.persistent_views) == 1


def test_post_profile_button_posts_for_admin():
    interaction = _FakeInteraction(perms=_FakePerms(manage_guild=True))
    cog = profiles_cog.ProfilesCog(bot=None)

    async def _run():
        await profiles_cog.ProfilesCog.post_profile_button.callback(
            cog, interaction
        )

    asyncio.run(_run())
    assert len(interaction.channel.sent) == 1
    posted = interaction.channel.sent[0]
    assert isinstance(posted["view"], profiles_cog.ProfileButtonView)
    assert posted["embed"].title == "Set up your GGA profile"
    assert interaction.response.sent == [
        ("Profile button posted in this channel.", {"ephemeral": True})
    ]


def test_post_profile_button_refuses_non_admin():
    interaction = _FakeInteraction(perms=_FakePerms())
    cog = profiles_cog.ProfilesCog(bot=None)

    async def _run():
        await profiles_cog.ProfilesCog.post_profile_button.callback(
            cog, interaction
        )

    asyncio.run(_run())
    assert interaction.channel.sent == []
    assert interaction.response.sent == [
        ("Only crew/admins can post the profile button.", {"ephemeral": True})
    ]
