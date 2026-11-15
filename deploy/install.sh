#!/usr/bin/env bash
# Install the GGA Profile Bot on a fresh Debian/Ubuntu VM
# (e.g. a Google Cloud e2-micro on the Always Free tier).
#
# Run it once, on the VM, as the normal user (sudo must work):
#   git clone https://github.com/wk7y2g9f5w-crypto/Flight-Bot.git
#   cd Flight-Bot && bash deploy/install.sh
#
# It installs Python + git, clones the bot to /opt/gga-profile-bot,
# asks for the Discord token and server ID (typed in hidden, never
# pasted into a chat), and installs a systemd service so the bot
# starts on boot and restarts itself if it crashes.
set -euo pipefail

APP_DIR="/opt/gga-profile-bot"
REPO="https://github.com/wk7y2g9f5w-crypto/Flight-Bot.git"

sudo apt-get update -y
sudo apt-get install -y python3 python3-venv git

if [ ! -d "$APP_DIR/.git" ]; then
  sudo git clone "$REPO" "$APP_DIR"
  sudo chown -R "$USER":"$USER" "$APP_DIR"
fi
cd "$APP_DIR"
git pull --ff-only || true
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt

if [ ! -f .env ]; then
  echo "Paste your Discord bot token (input is hidden):"
  read -r -s DISCORD_TOKEN
  echo
  echo "Paste the GGA server ID:"
  read -r GUILD_ID
  printf 'DISCORD_TOKEN=%s\nGUILD_ID=%s\nDB_PATH=%s\n' \
    "$DISCORD_TOKEN" "$GUILD_ID" "$APP_DIR/data/gga_profiles.db" > .env
  chmod 600 .env
fi
mkdir -p data

sudo tee /etc/systemd/system/gga-profile-bot.service > /dev/null <<EOF
[Unit]
Description=GGA Profile Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/.venv/bin/python -m src.bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now gga-profile-bot
sleep 3
sudo systemctl status gga-profile-bot --no-pager | head -20 || true
echo
echo "Watch the logs with: sudo journalctl -u gga-profile-bot -f"
echo "Look for: Logged in as GGA Profile Bot"
