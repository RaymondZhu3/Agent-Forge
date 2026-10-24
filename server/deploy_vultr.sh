#!/usr/bin/env bash
# One-shot API setup for a fresh Ubuntu 22.04/24.04 Vultr VM. Run as root on the VM:
#   REPO_URL=https://github.com/RaymondZhu3/Agent-Forge.git bash deploy_vultr.sh
# Put your .env at /opt/agent-forge/.env afterwards (never commit it), then: systemctl restart agentforge
set -euo pipefail

REPO_URL="${REPO_URL:?set REPO_URL}"
APP_DIR=/opt/agent-forge
PORT="${PORT:-8000}"

apt-get update -y
apt-get install -y python3 python3-venv python3-pip git ufw

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull --rebase
else
  git clone "$REPO_URL" "$APP_DIR"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"

cat > /etc/systemd/system/agentforge.service <<UNIT
[Unit]
Description=Agent Forge API
After=network-online.target

[Service]
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/uvicorn server.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

ufw allow OpenSSH
ufw allow "$PORT"/tcp
ufw --force enable

systemctl daemon-reload
systemctl enable agentforge
if [ -f "$APP_DIR/.env" ]; then
  systemctl restart agentforge
  sleep 3
  curl -s "http://127.0.0.1:$PORT/api/health" && echo
else
  echo "Now create $APP_DIR/.env, then run: systemctl restart agentforge"
fi
