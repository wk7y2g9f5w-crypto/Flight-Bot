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

## Setup — create the bot in Discord (needed whatever the host is)

1. Go to <https://discord.com/developers/applications> and sign in.
2. Click **New Application**, name it `GGA Profile Bot`, click Create.
3. On the left, click **Bot**, then **Reset Token** and copy the token.
   Keep it private — it is the bot's password. (If it ever leaks,
   reset it here and update the copy wherever the bot runs.)
4. On the same Bot page, scroll to **Privileged Gateway Intents** and
   turn on **Server Members Intent**. The welcome DM needs this.
5. On the left, click **OAuth2 → URL Generator**. Tick the scopes
   **bot** and **applications.commands**. Under Bot Permissions tick
   **Send Messages**. Copy the URL at the bottom, open it, and pick the
   GGA server to add the bot.

## Hosting — Google Cloud free VM (current plan)

Render can't create the paid worker until Dec 1, 2026 (card removed
from the workspace), so the bot runs on a Google Cloud e2-micro VM
on the Always Free tier instead: 1 vCPU / 1 GB RAM, $0 forever.

1. In the Google Cloud console, create a VM with these exact settings
   so it stays inside the free tier:
   - Region: **us-west1** (Oregon), zone us-west1-a
   - Machine type: **e2-micro**
   - Boot disk: Debian 12, **30 GB standard persistent disk**
   - Everything else default. No inbound firewall rules needed —
     the bot only talks out to Discord.
2. Click **SSH** on the VM to open a terminal, then run:
   ```bash
   git clone https://github.com/wk7y2g9f5w-crypto/Flight-Bot.git
   cd Flight-Bot && bash deploy/install.sh
   ```
   The script installs Python, sets up the bot at
   `/opt/gga-profile-bot`, asks for the Discord token and server ID
   (typed in hidden), and installs a systemd service so the bot
   starts on boot and restarts if it crashes.
3. Check the logs: `sudo journalctl -u gga-profile-bot -f` — look for
   `Logged in as GGA Profile Bot`.

## Hosting — Render (plan B, from Dec 1, 2026)

1. Push this folder to a GitHub repo (or use the "New +" → "Background
   Worker" → "Build and deploy from a Git repository" flow in Render).
2. Render reads `render.yaml` in this folder: it creates a background
   worker called `gga-profile-bot` with a 1 GB disk for the database.
3. In the Render dashboard, open the service → **Environment** and set:
   - `DISCORD_TOKEN` — the token from the Discord setup above.
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
