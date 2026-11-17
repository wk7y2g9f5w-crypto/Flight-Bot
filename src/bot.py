"""Entry point: python src/bot.py

Guild-scoped slash command sync when GUILD_ID is set (instant registration
while testing), otherwise global sync.
Needs the Server Members privileged intent (for the welcome DM on join).
"""
import asyncio
import os
import sys

import discord
from discord.ext import commands

from src import config, db
from src.cogs import profiles as profiles_cog

COGS = [
    "src.cogs.profiles",
    "src.cogs.roster",
    "src.cogs.welcome",
]


class GGAProfileBot(commands.Bot):
    def __init__(self):
        # Route through the egress proxy when one is configured (sandboxed envs).
        proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        intents = discord.Intents.default()
        intents.members = True  # privileged intent: on_member_join welcome DM
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            proxy=proxy_url,
        )
        self.db_path = config.DB_PATH

    async def setup_hook(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        await db.init_db(self.db_path)
        for ext in COGS:
            await self.load_extension(ext)
        # Persistent views must be re-registered on every startup or
        # their buttons stop responding after a restart.
        self.add_view(profiles_cog.ProfileButtonView())
        if config.GUILD_ID:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} commands to guild {config.GUILD_ID}")
        else:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} commands globally")

    async def on_ready(self):
        print(f"Logged in as {self.user} (id={self.user.id})")


async def main():
    if not config.DISCORD_TOKEN:
        print("DISCORD_TOKEN is not set — see README.md for setup.", file=sys.stderr)
        raise SystemExit(1)
    async with GGAProfileBot() as bot:
        await bot.start(config.DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
