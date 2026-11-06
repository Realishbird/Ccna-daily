#!/usr/bin/env bash
# Install or update CCNA Daily inside a Debian 12/13 (or Ubuntu) LXC or VM.
# Run as root:  bash install.sh
# Re-running it updates the app to the latest code and restarts the service.
set -euo pipefail

REPO="${CCNA_REPO:-https://github.com/Realishbird/ccna-daily.git}"
BRANCH="${CCNA_BRANCH:-main}"
APP_DIR="${CCNA_DIR:-/opt/ccna-daily}"
DATA_DIR="${CCNA_DATA:-/var/lib/ccna-daily}"
ENV_FILE=/etc/ccna-daily.env
PORT="${CCNA_PORT:-8080}"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (inside the container: pct enter <id>, then bash install.sh)." >&2
  exit 1
fi

echo "==> Installing packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git python3 python3-venv ca-certificates curl tzdata >/dev/null

echo "==> Creating service user"
id ccna >/dev/null 2>&1 || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin ccna
mkdir -p "$DATA_DIR"
chown ccna:ccna "$DATA_DIR"

echo "==> Fetching code ($BRANCH)"
if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
  git -C "$APP_DIR" checkout --quiet "$BRANCH"
  git -C "$APP_DIR" reset --quiet --hard "origin/$BRANCH"
else
  git clone --quiet --branch "$BRANCH" "$REPO" "$APP_DIR"
fi

echo "==> Python environment"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "==> Writing $ENV_FILE"
  TZ_GUESS="$(cat /etc/timezone 2>/dev/null || timedatectl show -p Timezone --value 2>/dev/null || echo America/New_York)"
  IP="$(hostname -I | awk '{print $1}')"
  cat >"$ENV_FILE" <<EOF
# CCNA Daily settings. Edit, then: systemctl restart ccna-daily
CCNA_DB=$DATA_DIR/ccna.db
CCNA_TZ=$TZ_GUESS
CCNA_START=$(date +%F)
CCNA_PORT=$PORT

# Reminders fire at these times only if today's session is not done.
CCNA_REMINDERS=12:00,19:00
# Phone push via the ntfy app: pick a hard-to-guess topic name and subscribe to it in the app.
CCNA_NTFY_URL=
# Or a Discord channel webhook URL.
CCNA_DISCORD_WEBHOOK=
# Link opened when you tap a reminder.
CCNA_APP_URL=http://$IP:$PORT

# Daily minimums
CCNA_NEW_CARDS=30
CCNA_DRILL_MIN=20
CCNA_QUESTIONS_MIN=20
CCNA_LABS_MIN=1
EOF
fi

echo "==> systemd service"
cat >/etc/systemd/system/ccna-daily.service <<EOF
[Unit]
Description=CCNA Daily study app
After=network-online.target
Wants=network-online.target

[Service]
User=ccna
Group=ccna
EnvironmentFile=$ENV_FILE
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python -m ccna_daily
Environment=PYTHONDONTWRITEBYTECODE=1
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$DATA_DIR
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --quiet ccna-daily
systemctl restart ccna-daily

sleep 2
PORT_NOW="$(. "$ENV_FILE"; echo "${CCNA_PORT:-8080}")"
if curl -fsS "http://127.0.0.1:$PORT_NOW/healthz" >/dev/null; then
  echo
  echo "CCNA Daily is running: http://$(hostname -I | awk '{print $1}'):$PORT_NOW"
  echo "Settings: $ENV_FILE   Logs: journalctl -u ccna-daily -f"
else
  echo "Service did not answer yet. Check: journalctl -u ccna-daily -n 50" >&2
  exit 1
fi
