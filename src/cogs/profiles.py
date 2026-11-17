"""/profile — each member records their Golf+ username, timezone /
playing time, Golf+ handicap, and preferred tour. Re-running the
command updates the profile: the form is pre-filled with the member's
current values.

Flow (a Discord modal can only hold text inputs, so the tour picker is a
separate step): /profile sends an ephemeral message with a tour select and
a button. The button opens the modal for the five text fields. Submitting
the modal saves everything at once.

Playing time is structured, not free text: the member enters the days
they usually play and a start–end window in their own timezone, and the
bot converts the window to Eastern Time for the roster. A modal holds at
most five text inputs, so the form is full — nothing else can be added
without dropping a field.
"""
import discord
from discord import app_commands
from discord.ext import commands

from src import config, db
from src.availability import (
    convert_window_to_eastern,
    format_eastern_display,
    format_window_local,
    local_tz_abbrev,
    parse_window,
    validate_timezone,
)
from src.validation import VALID_TOURS, format_handicap, parse_handicap


class ProfileModal(discord.ui.Modal):
    """The five text fields of the profile form."""

    def __init__(self, *, tour: str, existing: dict | None):
        super().__init__(title="Your GGA profile")
        self.tour = tour
        self.username_input = discord.ui.TextInput(
            label="Golf+ Username",
            placeholder="e.g. Alumec",
            default=(existing or {}).get("golfplus_username", ""),
            required=False,
            max_length=64,
        )
        self.timezone_input = discord.ui.TextInput(
            label="Timezone",
            placeholder="e.g. America/Denver",
            default=(existing or {}).get("timezone", ""),
            required=True,
            max_length=64,
        )
        self.days_input = discord.ui.TextInput(
            label="Days you usually play",
            placeholder="e.g. Weeknights",
            default=(existing or {}).get("avail_days", ""),
            required=True,
            max_length=64,
        )
        start_min = (existing or {}).get("avail_start_min")
        end_min = (existing or {}).get("avail_end_min")
        window_default = ""
        if start_min is not None and end_min is not None:
            window_default = format_window_local(start_min, end_min)
        self.window_input = discord.ui.TextInput(
            label="Playing window (your time)",
            placeholder="e.g. 6pm-9pm",
            default=window_default,
            required=True,
            max_length=32,
        )
        existing_handicap = (existing or {}).get("handicap")
        self.handicap_input = discord.ui.TextInput(
            label="Golf+ Handicap",
            placeholder="e.g. 12 or 12.5 (use +2 for a plus-handicap)",
            default="" if existing_handicap is None else format_handicap(existing_handicap),
            required=True,
            max_length=16,
        )
        self.add_item(self.username_input)
        self.add_item(self.timezone_input)
        self.add_item(self.days_input)
        self.add_item(self.window_input)
        self.add_item(self.handicap_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            handicap = parse_handicap(self.handicap_input.value)
            timezone = validate_timezone(self.timezone_input.value)
            days = self.days_input.value.strip()
            if not days:
                raise ValueError(
                    "Days are empty — enter something like Weeknights."
                )
            start_min, end_min = parse_window(self.window_input.value)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        est_start, est_end = convert_window_to_eastern(start_min, end_min, timezone)
        eastern_display = format_eastern_display(days, est_start, est_end)
        local_window = (
            f"{format_window_local(start_min, end_min)} "
            f"{local_tz_abbrev(timezone)}"
        )
        await db.upsert_profile(
            config.DB_PATH,
            discord_id=interaction.user.id,
            display_name=interaction.user.display_name,
            golfplus_username=self.username_input.value.strip(),
            timezone=timezone,
            available_time=eastern_display,
            avail_days=days,
            avail_start_min=start_min,
            avail_end_min=end_min,
            handicap=handicap,
            preferred_tour=self.tour,
        )
        embed = discord.Embed(
            title="Your GGA profile is saved",
            description="Run /profile anytime to update it.",
            colour=discord.Colour.green(),
        )
        embed.add_field(
            name="Golf+ Username",
            value=self.username_input.value.strip() or "—",
            inline=False,
        )
        embed.add_field(name="Timezone", value=timezone, inline=False)
        embed.add_field(
            name="Available playing time",
            value=f"{eastern_display}\nYour time: {local_window}",
            inline=False,
        )
        embed.add_field(name="Golf+ Handicap", value=format_handicap(handicap), inline=True)
        embed.add_field(name="Preferred Tour", value=self.tour, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TourSelect(discord.ui.Select):
    """Preferred-tour picker. The member's current tour is pre-selected."""

    def __init__(self, current: str | None):
        options = [
            discord.SelectOption(
                label="ProTour",
                description="No handicap — pure competition",
                default=(current == "ProTour"),
            ),
            discord.SelectOption(
                label="Accessible",
                description="Handicap-based, built for growth",
                default=(current == "Accessible"),
            ),
            discord.SelectOption(
                label="Both",
                description="Happy to play either tour",
                default=(current == "Both"),
            ),
        ]
        super().__init__(
            placeholder="Preferred Tour — ProTour, Accessible, or Both",
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ProfileSetupView = self.view  # type: ignore[assignment]
        view.tour = self.values[0]
        await interaction.response.defer()


class ProfileSetupView(discord.ui.View):
    """Ephemeral setup message: pick a tour, then open the details modal."""

    def __init__(self, *, existing: dict | None):
        super().__init__(timeout=600)
        current = (existing or {}).get("preferred_tour")
        self.tour: str | None = current if current in VALID_TOURS else None
        self.existing = existing
        self.add_item(TourSelect(current))

    @discord.ui.button(
        label="Enter username, timezone, playing time & handicap",
        style=discord.ButtonStyle.primary,
    )
    async def open_modal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not self.tour:
            await interaction.response.send_message(
                "Pick a Preferred Tour from the menu first.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(
            ProfileModal(tour=self.tour, existing=self.existing)
        )


class ProfilesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="profile",
        description="Set or update your Golf+ username, timezone, playing time, handicap, and tour.",
    )
    async def profile(self, interaction: discord.Interaction) -> None:
        existing = await db.get_profile(config.DB_PATH, interaction.user.id)
        message = (
            "Set your GGA profile — pick your tour, then fill in the details. "
            "You can run /profile again anytime to change it."
        )
        if (
            existing
            and existing.get("avail_start_min") is None
            and existing.get("available_time")
        ):
            # Saved before structured times: the old free-text entry
            # cannot be split into days + a window, so ask them to
            # re-enter it instead of silently dropping it.
            message += (
                f"\n\nYour current playing time is saved as "
                f'"{existing["available_time"]}" — re-enter it below as '
                "days + a time window."
            )
        await interaction.response.send_message(
            message,
            view=ProfileSetupView(existing=existing),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfilesCog(bot))
