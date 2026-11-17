"""Welcome DMs — when someone joins the server, DM them an invite to set
their GGA profile with /profile. If their DMs are closed, ignore silently.
"""
import discord
from discord.ext import commands


class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        embed = discord.Embed(
            title=f"Welcome to {member.guild.name}!",
            description=(
                "Before you jump in, set your GGA profile with the "
                "**/profile** command in the server. It takes a minute and "
                "helps the crew match you with the right games:\n\n"
                "• **Available playing time (Eastern Time)** — when you can play\n"
                "• **Golf+ Handicap** — so flights stay fair\n"
                "• **Preferred Tour** — ProTour, Accessible, or Both\n\n"
                "You can run /profile again anytime to update it."
            ),
            colour=discord.Colour.green(),
        )
        try:
            await member.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            # DMs closed or undeliverable — ignore silently, no error spam.
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
