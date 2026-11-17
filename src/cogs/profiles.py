"""/profile — each member records their Golf+ username, playing time
(in Eastern Time), Golf+ handicap, and preferred tour. Re-running the
command updates the profile: the form is pre-filled with the member's
current values.

Flow (a Discord modal can only hold text inputs, so the tour picker is a
separate step): /profile sends an ephemeral message with a tour select and
a button. The button opens the modal for the text fields. Submitting
the modal saves everything at once.

Some members struggle with typing the command, so a crew/admin can also
post a persistent "Set Up Your Profile" button in a channel
(/post-profile-button). Tapping it sends the member the same ephemeral
setup message /profile sends — no typing, no command menu.

No timezone is collected anymore: everyone enters their playing window
in Eastern Time, and the roster reads in Eastern Time. Profiles saved
before this change stored their window in their own timezone — when
such a member re-opens the form, the stored window is converted to
Eastern once for the prefill, so nobody's playing time silently shifts.

Playing time is structured, not free text: the member enters the days
they usually play and a start–end window in Eastern Time. A modal holds
at most five text inputs, so the form is full — nothing else can be added
without dropping a field.
"""
import discord
from discord import app_commands
from discord.ext import commands

from src import config, db
from src.availability import (
    convert_window_to_eastern,
    format_clock,
    format_eastern_display,
    format_window_local,
    parse_window,
)
from src.validation import VALID_TOURS, format_handicap, parse_handicap


class ProfileModal(discord.ui.Modal):
    """The text fields of the profile form (timezone is not asked)."""

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
            stored_tz = (existing or {}).get("timezone")
            if stored_tz:
                # Saved before timezones were removed: the stored window
                # is in the member's old timezone, so translate it to
                # Eastern once for the prefill — nobody's playing time
                # silently shifts. Falls back to the stored window if
                # the old zone name is somehow unreadable.
                try:
                    est_start, est_end = convert_window_to_eastern(
                        start_min, end_min, stored_tz
                    )
                    window_default = f"{est_start}-{est_end}"
                except Exception:
                    window_default = format_window_local(start_min, end_min)
            else:
                # Already stored in Eastern Time.
                window_default = format_window_local(start_min, end_min)
        self.window_input = discord.ui.TextInput(
            label="Playing window (Eastern Time)",
            placeholder="e.g. 6pm-9pm ET",
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
        self.add_item(self.days_input)
        self.add_item(self.window_input)
        self.add_item(self.handicap_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            handicap = parse_handicap(self.handicap_input.value)
            days = self.days_input.value.strip()
            if not days:
                raise ValueError(
                    "Days are empty — enter something like Weeknights."
                )
            # The window is entered in Eastern Time — no conversion.
            start_min, end_min = parse_window(self.window_input.value)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        eastern_display = format_eastern_display(
            days, format_clock(start_min), format_clock(end_min)
        )
        await db.upsert_profile(
            config.DB_PATH,
            discord_id=interaction.user.id,
            display_name=interaction.user.display_name,
            golfplus_username=self.username_input.value.strip(),
            timezone="",
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
        embed.add_field(
            name="Available playing time",
            value=eastern_display,
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
        label="Enter username, playing time & handicap",
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


class ProfileButtonView(discord.ui.View):
    """Persistent "Set Up Your Profile" button for a channel message.

    timeout=None plus a fixed custom_id so the button keeps working
    across bot restarts (re-registered in setup_hook). Tapping it sends
    the member the same ephemeral setup message /profile sends.
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Set Up Your Profile",
        style=discord.ButtonStyle.primary,
        custom_id="gga_profile_setup_button",
    )
    async def open_setup(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await send_profile_setup(interaction)


async def send_profile_setup(interaction: discord.Interaction) -> None:
    """Send the ephemeral setup message (tour picker + open-modal button).

    Shared by /profile and the persistent setup button, so both open
    exactly the same form.
    """
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
            "days + a time window (Eastern Time)."
        )
    await interaction.response.send_message(
        message,
        view=ProfileSetupView(existing=existing),
        ephemeral=True,
    )


class ProfilesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="profile",
        description="Set or update your Golf+ username, playing time (Eastern Time), handicap, and tour.",
    )
    async def profile(self, interaction: discord.Interaction) -> None:
        await send_profile_setup(interaction)

    @app_commands.command(
        name="post-profile-button",
        description="Post the 'Set Up Your Profile' button in this channel (crew/admin only).",
    )
    @app_commands.guild_only()
    async def post_profile_button(
        self, interaction: discord.Interaction
    ) -> None:
        perms = interaction.user.guild_permissions  # type: ignore[union-attr]
        if not (perms.administrator or perms.manage_guild):
            await interaction.response.send_message(
                "Only crew/admins can post the profile button.",
                ephemeral=True,
            )
            return
        if interaction.channel is None:
            await interaction.response.send_message(
                "Could not find this channel — try again from a server channel.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="Set up your GGA profile",
            description=(
                "Tap the button below and fill in your Golf+ username, "
                "playing time (Eastern Time), handicap, and preferred tour. "
                "It takes about a minute, and you can update it anytime."
            ),
            colour=discord.Colour.green(),
        )
        await interaction.channel.send(embed=embed, view=ProfileButtonView())
        await interaction.response.send_message(
            "Profile button posted in this channel.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfilesCog(bot))
