"""/roster — crew/admin view of saved member profiles.

Restricted to members with Administrator or Manage Server permission
(no hardcoded role names — GGA's role names are unknown). Replies
ephemerally. Shows the first 20 entries with a "Show more" button
that expands the same message to the full list.
"""
import discord
from discord import app_commands
from discord.ext import commands

from src import config, db
from src.expandable_list import COLLAPSED_LIMIT, ExpandableListView
from src.validation import format_handicap


class RosterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="roster",
        description="List saved member profiles (crew/admin only).",
    )
    @app_commands.describe(
        tour="Only show members who prefer this tour.",
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
        )
        if not profiles:
            await interaction.response.send_message(
                "No saved profiles match those filters yet.",
                ephemeral=True,
            )
            return
        lines = [
            f"**{p['display_name']}** — Golf+ {p['golfplus_username'] or '—'} | "
            f"{p['available_time'] or '—'} | "
            f"HCP {format_handicap(p['handicap'])} | {p['preferred_tour']}"
            for p in profiles
        ]
        view = ExpandableListView(
            title=f"GGA member roster ({len(profiles)} saved)",
            lines=lines,
            invoker_id=interaction.user.id,
            colour=discord.Colour.blue(),
            collapsed_footer=(
                f"Showing the first {COLLAPSED_LIMIT} of {len(profiles)} — "
                "narrow it down with the tour filter."
            ),
            expanded_footer=f"Showing all {len(profiles)}.",
        )
        await interaction.response.send_message(
            embed=view.build_embed(),
            view=view if view.has_expand else None,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RosterCog(bot))
