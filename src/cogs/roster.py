"""/roster — crew/admin view of saved member profiles.

Restricted to members with Administrator or Manage Server permission
(no hardcoded role names — GGA's role names are unknown). Replies
ephemerally and caps the list at 20 entries.
"""
import discord
from discord import app_commands
from discord.ext import commands

from src import config, db

MAX_ENTRIES = 20


def _format_handicap(handicap) -> str:
    return f"{handicap:g}" if handicap is not None else "—"


class RosterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="roster",
        description="List saved member profiles (crew/admin only).",
    )
    @app_commands.describe(
        tour="Only show members who prefer this tour.",
        timezone="Only show members whose timezone contains this text.",
    )
    @app_commands.choices(
        tour=[
            app_commands.Choice(name="ProTour", value="ProTour"),
            app_commands.Choice(name="Accessible", value="Accessible"),
            app_commands.Choice(name="Both", value="Both"),
        ]
    )
    @app_commands.guild_only()
    async def roster(
        self,
        interaction: discord.Interaction,
        tour: str | None = None,
        timezone: str | None = None,
    ) -> None:
        perms = interaction.user.guild_permissions  # type: ignore[union-attr]
        if not (perms.administrator or perms.manage_guild):
            await interaction.response.send_message(
                "Only crew/admins can view the roster.",
                ephemeral=True,
            )
            return
        profiles = await db.list_profiles(
            config.DB_PATH,
            tour=tour,
            timezone=timezone.strip() if timezone else None,
        )
        if not profiles:
            await interaction.response.send_message(
                "No saved profiles match those filters yet.",
                ephemeral=True,
            )
            return
        shown = profiles[:MAX_ENTRIES]
        lines = []
        for p in shown:
            lines.append(
                f"**{p['display_name']}** — Golf+ {p['golfplus_username'] or '—'} | "
                f"{p['timezone'] or '—'} | "
                f"{p['available_time'] or '—'} | "
                f"HCP {_format_handicap(p['handicap'])} | {p['preferred_tour']}"
            )
        embed = discord.Embed(
            title=f"GGA member roster ({len(profiles)} saved)",
            description="\n".join(lines),
            colour=discord.Colour.blue(),
        )
        if len(profiles) > MAX_ENTRIES:
            embed.set_footer(
                text=f"Showing the first {MAX_ENTRIES} of {len(profiles)} — "
                "narrow it down with the tour or timezone filter."
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RosterCog(bot))
