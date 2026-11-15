# GGA Profile Bot

A small Discord bot for the GGA golf community. It collects four things
from every member so the crew can build flights and TeamGolf squads:

1. **Golf+ Username** — their in-game handle
2. **Timezone / available playing time** — when they can play
3. **Golf+ Handicap** — so flights stay fair
4. **Preferred Tour** — ProTour, Accessible, or Both

Members can update their info anytime by running `/profile` again.

## What the bot does

- **`/profile`** — opens a short form. Pick your tour from a menu, then
  enter your Golf+ username, your timezone (like `America/Denver`),
  your usual playing times (like "Weeknights after 6pm MT, weekend
  mornings"), and your Golf+ handicap. The bot saves it and shows you
  a summary. Run it again anytime to change anything — the form comes
  pre-filled with your current answers. (The Golf+ username is
  optional; the handicap is required.)
- **`/roster`** — crew/admins only. Lists everyone's saved profiles
  (name, Golf+ username, timezone, playing time, handicap, tour). You can narrow it
  down by tour or by timezone. Only people with Administrator or
  Manage Server permission can use it.
- **Welcome DM** — when someone new joins the server, the bot sends
  them a private message inviting them to set their profile with
  `/profile`. If their DMs are closed, the bot just skips them quietly.

Profiles are stored in a small SQLite database file. Nothing else is
stored, and nothing leaves the server.

## Setup (Cayden — about 15 minutes)

### 1. Create the bot in the Discord Developer Portal

1. Go to <https://discord.com/developers/applications> and sign in.
2. Click **New Application**, name it `GGA Profile Bot`, click Create.
3. On the left, click **Bot**, then **Reset Token** and copy the token.
   Keep it private — it is the bot's password. (If it ever leaks,
   reset it here and update the copy on Render.)
4. On the same Bot page, scroll to **Privileged Gateway Intents** and
   turn on **Server Members Intent**. The welcome DM needs this.
5. On the left, click **OAuth2 → URL Generator**. Tick the scopes
   **bot** and **applications.commands**. Under Bot Permissions tick
   **Send Messages**. Copy the URL at the bottom, open it, and pick the
   GGA server to add the bot.

### 2. Deploy on Render

1. Push this folder to a GitHub repo (or use the "New +" → "Background
   Worker" → "Build and deploy from a Git repository" flow in Render).
2. Render reads `render.yaml` in this folder: it creates a background
   worker called `gga-profile-bot` with a 1 GB disk for the database.
3. In the Render dashboard, open the service → **Environment** and set:
   - `DISCORD_TOKEN` — the token from step 1.
   - `GUILD_ID` — the GGA server's ID. This makes the `/profile` and
     `/roster` commands show up instantly. To find it: in Discord,
     turn on Developer Mode (Settings → Advanced), right-click the
     server name, Copy Server ID. You can leave it blank and the bot
     will register the commands globally instead, but that can take up
     to an hour to appear.
4. Deploy. In the logs you should see `Synced 2 commands to guild ...`
   and `Logged in as GGA Profile Bot ...`.

## Running it on your own computer (testing)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then put your token and guild ID in .env
.venv/bin/python src/bot.py
```

Run the tests with:

```bash
.venv/bin/python -m pytest tests/ -q
```

(The tests were developed and run with the companion app's venv at
`~/workspace/golf-companion-app/.venv/bin/python`, which already has
discord.py 2.7.1, aiosqlite, and pytest installed.)

## Files

- `src/bot.py` — starts the bot, loads the cogs, registers the commands.
- `src/config.py` — reads settings from the environment.
- `src/db.py` — the SQLite storage (one table: `member_profiles`).
- `src/validation.py` — handicap and tour checks.
- `src/cogs/profiles.py` — the `/profile` command and form.
- `src/cogs/roster.py` — the `/roster` command for crew/admins.
- `src/cogs/welcome.py` — the welcome DM for new members.
- `tests/` — pytest tests for the database, validation, and cog loading.
- `render.yaml` — Render background worker + disk setup.
