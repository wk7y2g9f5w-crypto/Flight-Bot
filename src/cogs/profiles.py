"""/profile — each member records their Golf+ username, timezone /
playing time, Golf+ handicap, and preferred tour. Re-running the
command updates the profile: the form is pre-filled with the member's
current values.

Flow (a Discord modal can only hold text inputs, so the tour picker is a
separate step): /profile sends an ephemeral message with a tour select and
a button. The button opens the modal for the four text fields. Submitting
the modal saves everything at once.
"""
import discord
from discord import app_commands
from discord.ext import commands

from src import config, db
from src.validation import VALID_TOURS, parse_handicap


class ProfileModal(discord.ui.Modal):
    """The four text fields of the profile form."""

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
        self.time_input = discord.ui.TextInput(
            label="Available playing time",
            placeholder="e.g. Weeknights after 6pm MT, weekend mornings",
            default=(existing or {}).get("available_time", ""),
            required=True,
            max_length=200,
        )
        existing_handicap = (existing or {}).get("handicap")
        self.handicap_input = discord.ui.TextInput(
            label="Golf+ Handicap",
            placeholder="e.g. 12 or 12.5 (use -2 for a plus-handicap)",
            default="" if existing_handicap is None else f"{existing_handicap:g}",
            required=True,
            max_length=16,
        )
        self.add_item(self.username_input)
        self.add_item(self.timezone_input)
        self.add_item(self.time_input)
        self.add_item(self.handicap_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            handicap = parse_handicap(self.handicap_input.value)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await db.upsert_profile(
            config.DB_PATH,
            discord_id=interaction.user.id,
            display_name=interaction.user.display_name,
            golfplus_username=self.username_input.value.strip(),
            timezone=self.timezone_input.value.strip(),
            available_time=self.time_input.value.strip(),
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
        embed.add_field(name="Timezone", value=self.timezone_input.value.strip(), inline=False)
        embed.add_field(
            name="Available playing time",
            value=self.time_input.value.strip(),
            inline=False,
        )
        embed.add_field(name="Golf+ Handicap", value=f"{handicap:g}", inline=True)
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
        await interaction.response.send_message(
            "Set your GGA profile — pick your tour, then fill in the details. "
            "You can run /profile again anytime to change it.",
            view=ProfileSetupView(existing=existing),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ProfilesCog(bot))
