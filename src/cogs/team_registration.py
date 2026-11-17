"""/register-team — Team League registration, separate from /profile.

Same form as /profile minus the tour (Golf+ username, days, playing
window in Eastern Time, handicap), saved in its own table so the crew
can count exactly who signed up for the team league. Registering for
the team does not create or change a member's profile, and a profile
is not required to register — if one exists, the form is pre-filled
from it (or from the member's existing team registration, which takes
precedence). Re-running the command updates the registration.

Commands: /register-team (the form), /unregister-team (pull out),
/team-roster (crew/admin list + player count),
/post-team-button (crew/admin posts the persistent button).
"""
import discord
from discord import app_commands
from discord.ext import commands

from src import config, db
from src.availability import (
    format_clock,
    format_eastern_display,
    parse_window,
    prefill_window,
)
from src.validation import format_handicap, parse_handicap

MAX_ENTRIES = 20


class TeamModal(discord.ui.Modal):
    """The text fields of the team registration form."""

    def __init__(self, *, existing: dict | None):
        super().__init__(title="Register for the Team League")
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
        self.window_input = discord.ui.TextInput(
            label="Playing window (Eastern Time)",
            placeholder="e.g. 6pm-9pm ET",
            default=prefill_window(existing),
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
        await db.upsert_team_registration(
            config.DB_PATH,
            discord_id=interaction.user.id,
            display_name=interaction.user.display_name,
            golfplus_username=self.username_input.value.strip(),
            available_time=eastern_display,
            avail_days=days,
            avail_start_min=start_min,
            avail_end_min=end_min,
            handicap=handicap,
        )
        embed = discord.Embed(
            title="You're registered for the Team League",
            description=(
                "Run /register-team again anytime to update it, "
                "or /unregister-team to pull out."
            ),
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
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TeamSetupView(discord.ui.View):
    """Ephemeral setup message: tap the button to open the details modal."""

    def __init__(self, *, existing: dict | None):
        super().__init__(timeout=600)
        self.existing = existing

    @discord.ui.button(
        label="Enter username, playing time & handicap",
        style=discord.ButtonStyle.primary,
    )
    async def open_modal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            TeamModal(existing=self.existing)
        )


class TeamButtonView(discord.ui.View):
    """Persistent "Register for Team" button for a channel message.

    timeout=None plus a fixed custom_id so the button keeps working
    across bot restarts (re-registered in setup_hook). Tapping it sends
    the member the same ephemeral setup message /register-team sends.
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Register for Team",
        style=discord.ButtonStyle.primary,
        custom_id="gga_team_register_button",
    )
    async def open_setup(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await send_team_setup(interaction)


async def send_team_setup(interaction: discord.Interaction) -> None:
    """Send the ephemeral setup message (open-modal button).

    Shared by /register-team and the persistent register button, so both
    open exactly the same form. Prefills from the member's existing team
    registration if they have one, else from their profile.
    """
    team_reg = await db.get_team_registration(
        config.DB_PATH, interaction.user.id
    )
    existing = team_reg
    message = (
        "Register for the GGA Team League — fill in your Golf+ username, "
        "playing time (Eastern Time), and handicap. You can run "
        "/register-team again anytime to change it, or /unregister-team "
        "to pull out."
    )
    if existing is None:
        existing = await db.get_profile(config.DB_PATH, interaction.user.id)
        if (
            existing
            and existing.get("avail_start_min") is None
            and existing.get("available_time")
        ):
            # Profile saved before structured times: the old free-text
            # entry cannot be split into days + a window, so ask them
            # to re-enter it instead of silently dropping it.
            message += (
                f"\n\nYour profile's playing time is saved as "
                f'"{existing["available_time"]}" — re-enter it below as '
                "days + a time window (Eastern Time)."
            )
    await interaction.response.send_message(
        message,
        view=TeamSetupView(existing=existing),
        ephemeral=True,
    )


class TeamRegistrationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="register-team",
        description="Register for the GGA Team League — same form as /profile, counted separately.",
    )
    @app_commands.guild_only()
    async def register_team(self, interaction: discord.Interaction) -> None:
        await send_team_setup(interaction)

    @app_commands.command(
        name="unregister-team",
        description="Pull out of the Team League (removes your team registration).",
    )
    @app_commands.guild_only()
    async def unregister_team(self, interaction: discord.Interaction) -> None:
        existing = await db.get_team_registration(
            config.DB_PATH, interaction.user.id
        )
        if existing is None:
            await interaction.response.send_message(
                "You aren't registered for the team league.",
                ephemeral=True,
            )
            return
        await db.delete_team_registration(config.DB_PATH, interaction.user.id)
        await interaction.response.send_message(
            "You're no longer registered for the team league. "
            "Run /register-team anytime to sign back up.",
            ephemeral=True,
        )

    @app_commands.command(
        name="team-roster",
        description="List everyone registered for the Team League, with the player count (crew/admin only).",
    )
    @app_commands.guild_only()
    async def team_roster(
        self,
        interaction: discord.Interaction,
    ) -> None:
        perms = interaction.user.guild_permissions  # type: ignore[union-attr]
        if not (perms.administrator or perms.manage_guild):
            await interaction.response.send_message(
                "Only crew/admins can view the team roster.",
                ephemeral=True,
            )
            return
        registrations = await db.list_team_registrations(config.DB_PATH)
        embed = discord.Embed(
            title=f"Team League roster — {len(registrations)} registered",
            colour=discord.Colour.green(),
        )
        if not registrations:
            embed.description = "Nobody has registered for the team league yet."
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        lines = []
        for r in registrations[:MAX_ENTRIES]:
            lines.append(
                f"**{r['display_name']}** — Golf+ {r['golfplus_username'] or '—'} | "
                f"{r['available_time'] or '—'} | "
                f"HCP {format_handicap(r['handicap'])}"
            )
        embed.description = "\n".join(lines)
        if len(registrations) > MAX_ENTRIES:
            embed.set_footer(
                text=f"Showing the first {MAX_ENTRIES} of {len(registrations)}."
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="post-team-button",
        description="Post the 'Register for Team' button in this channel (crew/admin only).",
    )
    @app_commands.guild_only()
    async def post_team_button(
        self, interaction: discord.Interaction
    ) -> None:
        perms = interaction.user.guild_permissions  # type: ignore[union-attr]
        if not (perms.administrator or perms.manage_guild):
            await interaction.response.send_message(
                "Only crew/admins can post the team button.",
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
            title="Register for the GGA Team League",
            description=(
                "Tap the button below and fill in your Golf+ username, "
                "playing time (Eastern Time), and handicap. "
                "Everyone who wants to play in the team league needs to "
                "register — it takes about a minute, and you can update it "
                "anytime."
            ),
            colour=discord.Colour.green(),
        )
        await interaction.channel.send(embed=embed, view=TeamButtonView())
        await interaction.response.send_message(
            "Team button posted in this channel.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TeamRegistrationCog(bot))
