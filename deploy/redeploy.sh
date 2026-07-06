#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/ubuntu/audio-transcriber-bot"
SERVICE_NAME="audio-transcriber-bot"

cd "$APP_DIR"

git pull --ff-only

"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r requirements.txt

systemctl restart "$SERVICE_NAME"
systemctl status "$SERVICE_NAME" --no-pager
