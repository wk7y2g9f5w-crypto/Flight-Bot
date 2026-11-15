"""Bot configuration loaded from environment (.env supported)."""
import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "").strip()

# Guild ID for guild-scoped slash command registration (instant updates while
# testing). If 0/empty, commands sync globally (can take up to an hour).
_guild_raw = os.getenv("GUILD_ID", "").strip()
GUILD_ID: int = int(_guild_raw) if _guild_raw.isdigit() else 0

# SQLite file for member profiles. On Render this points at the persistent
# disk (see render.yaml); locally it defaults to ./data/gga_profiles.db.
DB_PATH: str = os.getenv("DB_PATH", "data/gga_profiles.db")
