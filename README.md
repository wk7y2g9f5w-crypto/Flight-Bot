# GGA Profile Bot

A small Discord bot for the GGA golf community. It collects four things
from every member so the crew can build flights and TeamGolf squads:

1. **Golf+ Username** — their in-game handle
2. **Available playing time (Eastern Time)** — when they can play, entered in Eastern Time
3. **Golf+ Handicap** — so flights stay fair
4. **Preferred Tour** — ProTour, Accessible, or Both

Members can update their info anytime by running `/profile` again — or
by tapping the **Set Up Your Profile** button, if a crew/admin has
posted it in a channel (see `/post-profile-button` below). Both open
the same form.

Separately, anyone who wants to play in the **Team League** registers
with **`/register-team`** — the same form as `/profile`, saved on its
own so the crew can count exactly who signed up. See the Team League
section below.

## What the bot does

- **`/profile`** — opens a short form. Pick your tour from a menu, then
  enter your Golf+ username, the days you usually play
  (like "Weeknights"), and a playing window in **Eastern Time** (like
  "6pm-9pm ET"). Everything is in Eastern Time, so the roster reads in
  one timezone. Run it again anytime to change anything — the form
  comes pre-filled with your current answers, with older windows
  translated to Eastern. (The Golf+ username is optional; the handicap
  is required.) Profiles saved before structured times keep their old
  free-text entry until the member re-saves.
- **`/setup-profile-for`** — crew/admins only. Same form as
  `/profile`, but for another member: pick the member, fill in their
  Golf+ username, days, playing window in Eastern Time, handicap, and
  tour, and it saves under their profile — not yours. The form comes
  pre-filled from their existing profile if they have one.
- **`/post-profile-button`** — crew/admins only. Posts a persistent
  **Set Up Your Profile** button in the channel where you run it, for
  members who struggle with typing the command. Tapping the button
  sends that member the same setup form `/profile` sends. The button
  keeps working across bot restarts. If the message is ever deleted,
  run the command again to post a fresh one.
- **`/roster`** — crew/admins only. Lists everyone's saved profiles
  (name, Golf+ username, playing time in Eastern Time,
  handicap, tour). You can narrow it down by tour. Only
  people with Administrator or Manage Server permission can use it.
- **`/register-team`** — opens the Team League form: the same fields
  as `/profile` minus the tour (Golf+ username, days, playing window in
  Eastern Time, handicap), saved separately in its own table so the
  crew can count signups. A profile is not required — if one exists,
  the form comes pre-filled from it (or from an existing team
  registration). Run it again anytime to update a registration.
- **`/unregister-team`** — pulls you out of the Team League (deletes
  your team registration; your profile is untouched).
- **`/register-team-for`** — crew/admins only. Same form as
  `/register-team`, but for another member — it saves under their
  registration, not yours. Pre-filled from their existing registration
  (or their profile).
- **`/unregister-team-for`** — crew/admins only. Pulls another member
  out of the Team League.
- **`/team-roster`** — crew/admins only. Lists everyone registered
  for the Team League, with the total player count in the title.
  Separate from `/roster`.
- **`/post-team-button`** — crew/admins only. Posts a persistent
  **Register for Team** button in the channel where you run it, the
  same as the profile button. Tapping it registers that member on the
  spot under their Discord name — the form it opens is just for the
  details (Golf+ username, playing time, handicap), and skipping it
  still leaves them on the roster. Tapping it again later just opens
  the form to update — it never wipes what they already entered.
- **`/post-roster`** — admins only. Posts the public team roster in
  the channel where you run it: just Golf+ usernames, one per line,
  with the total count — no playing times, no handicaps — so every
  member can see who's signed up. It updates itself whenever someone
  registers or unregisters. Run it again to move the roster to
  another channel (the old copy is taken down so there's never two
  lists). If the posted message is ever deleted, run it again to post
  a fresh one.
- **Welcome DM** — when someone new joins the server, the bot sends
  them a private message inviting them to set their profile with
  `/profile`. If their DMs are closed, the bot just skips them quietly.

Profiles and team registrations are stored in a small SQLite database
file. Nothing else is stored, and nothing leaves the server.

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
4. Deploy. In the logs you should see `Synced 11 commands to guild ...`
   and `Logged in as GGA Profile Bot ...`.

## Running it on your own computer (testing)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # then put your token and guild ID in .env
.venv/bin/python -m src.bot
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
- `src/db.py` — the SQLite storage (three tables: `member_profiles`,
  `team_registrations`, and `roster_posts`).
- `src/validation.py` — handicap and tour checks.
- `src/availability.py` — playing-time parsing and conversion to
  Eastern Time.
- `src/cogs/profiles.py` — the `/profile` command and form, the
  persistent setup button, `/post-profile-button`, and
  `/setup-profile-for` (crew/admin sets up another member's profile).
- `src/cogs/roster.py` — the `/roster` command for crew/admins.
- `src/cogs/team_registration.py` — `/register-team`,
  `/unregister-team`, `/team-roster`, the persistent register button,
  `/post-team-button`, `/post-roster` (public live-updating roster),
  and `/register-team-for` / `/unregister-team-for` (crew/admin acts
  for another member).
- `src/cogs/welcome.py` — the welcome DM for new members.
- `tests/` — pytest tests for the database, validation, availability
  conversion, and cog loading.
- `render.yaml` — Render background worker + disk setup.
