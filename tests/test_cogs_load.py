"""Cogs load onto a Bot instance without connecting to Discord.

No login, no network — add_cog only, then check the slash commands
registered on the command tree.
"""
import discord
from discord.ext import commands

from src.cogs import profiles as profiles_cog
from src.cogs import roster as roster_cog
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
        await bot.add_cog(welcome_cog.WelcomeCog(bot))

    asyncio.run(_load())
    names = {cmd.name for cmd in bot.tree.get_commands()}
    assert names == {"profile", "roster"}


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
    values = {child.label: child.default for child in modal.children}
    assert values["Golf+ Username"] == "Alumec"
    assert values["Timezone"] == "America/Denver"
    assert values["Days you usually play"] == "Weeknights"
    assert values["Playing window (your time)"] == "6pm-9pm"
    assert values["Golf+ Handicap"] == "12.5"


def test_profile_modal_leaves_days_and_window_blank_for_legacy_profile():
    # Saved before structured times: the free-text entry cannot be
    # split into days + a window, so the new fields start empty.
    existing = {
        "golfplus_username": "Alumec",
        "timezone": "America/Denver",
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
    assert values["Playing window (your time)"] == ""


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
