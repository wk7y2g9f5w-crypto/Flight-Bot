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
/post-team-button (crew/admin posts the persistent button),
/register-team-for and /unregister-team-for (crew/admin set up or
pull out another member — same form, saved under their row),
/post-roster (admin posts the public Golf+ username roster, which
updates itself whenever registrations change).
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


def build_roster_embed(registrations):
    """Public roster embed: Golf+ usernames only, one per line.

    A member without a Golf+ username shows under their Discord
    display name instead, so nobody who registered is missing from
    the list. Sorted by the name shown.
    """
    names = sorted(
        (r["golfplus_username"] or r["display_name"] for r in registrations),
        key=str.lower,
    )
    embed = discord.Embed(
        title=f"Team League roster — {len(names)} registered",
        colour=discord.Colour.green(),
    )
    embed.description = (
        "\n".join(names)
        if names
        else "Nobody has registered for the team league yet."
    )
    return embed


async def refresh_roster_posts(bot, guild_id):
    """Rebuild every posted public roster for a guild, in place.

    Called whenever a registration changes. A post whose message is
    gone (deleted, or the bot lost access) is forgotten so it is not
    retried on every change.
    """
    if bot is None or guild_id is None:
        return
    posts = await db.list_roster_posts(config.DB_PATH, guild_id)
    if not posts:
        return
    embed = build_roster_embed(
        await db.list_team_registrations(config.DB_PATH)
    )
    for channel_id, message_id in posts:
        try:
            channel = bot.get_channel(channel_id)
            if channel is None:
                channel = await bot.fetch_channel(channel_id)
            message = await channel.fetch_message(message_id)
            await message.edit(embed=embed)
        except Exception:
            await db.remove_roster_post(
                config.DB_PATH,
                guild_id=guild_id,
                channel_id=channel_id,
                message_id=message_id,
            )


class TeamModal(discord.ui.Modal):
    """The text fields of the team registration form.

    ``target`` is the member the form is being filled in for — None
    means the person submitting it (the usual /register-team flow); a
    crew/admin registering someone else passes that member here, and
    the save lands on their row, not the admin's.
    """

    def __init__(
        self, *, existing: dict | None, target: discord.Member | None = None
    ):
        title = (
            f"Register {target.display_name} for the Team League"[:45]
            if target
            else "Register for the Team League"
        )
        super().__init__(title=title)
        self.target = target
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
        member_id = self.target.id if self.target else interaction.user.id
        member_name = (
            self.target.display_name
            if self.target
            else interaction.user.display_name
        )
        await db.upsert_team_registration(
            config.DB_PATH,
            discord_id=member_id,
            display_name=member_name,
            golfplus_username=self.username_input.value.strip(),
            available_time=eastern_display,
            avail_days=days,
            avail_start_min=start_min,
            avail_end_min=end_min,
            handicap=handicap,
        )
        # A new or updated registration refreshes the posted public
        # roster, if an admin has posted one.
        await refresh_roster_posts(
            getattr(interaction, "client", None),
            getattr(interaction, "guild_id", None),
        )
        embed = discord.Embed(
            title=(
                f"{member_name} is registered for the Team League"
                if self.target
                else "You're registered for the Team League"
            ),
            description=(
                f"Set by an admin — {member_name} can run /register-team "
                "anytime to update it, or /unregister-team to pull out."
                if self.target
                else "Run /register-team again anytime to update it, "
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

    def __init__(self, *, existing: dict | None, target=None):
        super().__init__(timeout=600)
        self.existing = existing
        self.target = target

    @discord.ui.button(
        label="Enter username, playing time & handicap",
        style=discord.ButtonStyle.primary,
    )
    async def open_modal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(
            TeamModal(existing=self.existing, target=self.target)
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


async def send_team_setup_for(
    interaction: discord.Interaction, target: discord.Member
) -> None:
    """Same setup message as /register-team, but for another member.

    Sent ephemerally to the admin who ran /register-team-for; the
    form is pre-filled from the target's team registration (or their
    profile) and the save lands on their row, not the admin's.
    """
    team_reg = await db.get_team_registration(
        config.DB_PATH, target.id
    )
    existing = team_reg
    message = (
        f"Register {target.display_name} for the GGA Team League — fill in "
        "their Golf+ username, playing time (Eastern Time), and handicap. "
        "This saves to their registration, not yours."
    )
    if existing is None:
        existing = await db.get_profile(config.DB_PATH, target.id)
        if (
            existing
            and existing.get("avail_start_min") is None
            and existing.get("available_time")
        ):
            # Profile saved before structured times: the old free-text
            # entry cannot be split into days + a window, so ask the
            # admin to re-enter it instead of silently dropping it.
            message += (
                f"\n\nTheir profile's playing time is saved as "
                f'"{existing["available_time"]}" — re-enter it below as '
                "days + a time window (Eastern Time)."
            )
    await interaction.response.send_message(
        message,
        view=TeamSetupView(existing=existing, target=target),
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
        name="register-team-for",
        description="Register another member for the Team League (crew/admin only).",
    )
    @app_commands.guild_only()
    async def register_team_for(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        perms = interaction.user.guild_permissions  # type: ignore[union-attr]
        if not (perms.administrator or perms.manage_guild):
            await interaction.response.send_message(
                "Only crew/admins can register other members for the team league.",
                ephemeral=True,
            )
            return
        if member.bot:
            await interaction.response.send_message(
                "Bots don't play in the Team League.",
                ephemeral=True,
            )
            return
        await send_team_setup_for(interaction, member)

    @app_commands.command(
        name="unregister-team-for",
        description="Pull another member out of the Team League (crew/admin only).",
    )
    @app_commands.guild_only()
    async def unregister_team_for(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        perms = interaction.user.guild_permissions  # type: ignore[union-attr]
        if not (perms.administrator or perms.manage_guild):
            await interaction.response.send_message(
                "Only crew/admins can pull other members out of the team league.",
                ephemeral=True,
            )
            return
        existing = await db.get_team_registration(
            config.DB_PATH, member.id
        )
        if existing is None:
            await interaction.response.send_message(
                f"{member.display_name} isn't registered for the team league.",
                ephemeral=True,
            )
            return
        await db.delete_team_registration(config.DB_PATH, member.id)
        await refresh_roster_posts(
            self.bot, getattr(interaction, "guild_id", None)
        )
        await interaction.response.send_message(
            f"{member.display_name} is no longer registered for the team "
            "league.",
            ephemeral=True,
        )

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
        await refresh_roster_posts(
            self.bot, getattr(interaction, "guild_id", None)
        )
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

    @app_commands.command(
        name="post-roster",
        description="Post the public team roster — Golf+ usernames only — in this channel (admin only).",
    )
    @app_commands.guild_only()
    async def post_roster(
        self, interaction: discord.Interaction
    ) -> None:
        perms = interaction.user.guild_permissions  # type: ignore[union-attr]
        if not (perms.administrator or perms.manage_guild):
            await interaction.response.send_message(
                "Only admins can post the team roster.",
                ephemeral=True,
            )
            return
        if interaction.channel is None or interaction.guild_id is None:
            await interaction.response.send_message(
                "Could not find this channel — try again from a server channel.",
                ephemeral=True,
            )
            return
        # One live roster: take down any earlier posted copy first, so
        # members never see two lists that disagree.
        if self.bot is not None:
            for channel_id, message_id in await db.list_roster_posts(
                config.DB_PATH, interaction.guild_id
            ):
                try:
                    channel = self.bot.get_channel(channel_id)
                    if channel is None:
                        channel = await self.bot.fetch_channel(channel_id)
                    message = await channel.fetch_message(message_id)
                    await message.delete()
                except Exception:
                    pass
        await db.clear_roster_posts(config.DB_PATH, interaction.guild_id)
        embed = build_roster_embed(
            await db.list_team_registrations(config.DB_PATH)
        )
        posted = await interaction.channel.send(embed=embed)
        await db.add_roster_post(
            config.DB_PATH,
            guild_id=interaction.guild_id,
            channel_id=posted.channel.id,
            message_id=posted.id,
        )
        await interaction.response.send_message(
            "Team roster posted in this channel — it updates itself when "
            "players register or unregister. Run /post-roster again to "
            "move it to another channel.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TeamRegistrationCog(bot))
