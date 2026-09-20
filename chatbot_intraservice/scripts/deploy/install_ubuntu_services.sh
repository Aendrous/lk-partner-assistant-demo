#!/usr/bin/env bash
# One-time production installation. Run with sudo from the deployment account.
set -euo pipefail

SOURCE=/home/fetisovaa/iek-assistant
TARGET=/opt/iek-assistant

if [ ! -d "$SOURCE" ]; then
    echo "Source directory is missing: $SOURCE" >&2
    exit 1
fi
if [ -e "$TARGET" ]; then
    echo "Target already exists: $TARGET" >&2
    exit 1
fi

id -u iekbot >/dev/null 2>&1 || useradd --system --create-home --home-dir /opt/iekbot --shell /usr/sbin/nologin iekbot
mv "$SOURCE" "$TARGET"
chown -R iekbot:iekbot "$TARGET"
chmod 600 "$TARGET/chatbot_intraservice/.env"

install -m 644 "$TARGET/chatbot_intraservice/scripts/deploy/iek-l0-ui.service" /etc/systemd/system/iek-l0-ui.service
install -m 644 "$TARGET/chatbot_intraservice/scripts/deploy/iek-l1-ui.service" /etc/systemd/system/iek-l1-ui.service
install -m 644 "$TARGET/chatbot_intraservice/scripts/deploy/iek-intraservice-n8n-api.service" /etc/systemd/system/iek-intraservice-n8n-api.service

systemctl daemon-reload
systemctl enable --now iek-l0-ui iek-l1-ui iek-intraservice-n8n-api
systemctl --no-pager --full status iek-l0-ui iek-l1-ui iek-intraservice-n8n-api
