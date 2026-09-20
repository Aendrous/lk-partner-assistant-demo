#!/usr/bin/env bash
set -euo pipefail

chmod 755 /etc/nginx/ssl /etc/nginx/ssl/chatbot.iek.local
nginx -t
systemctl restart nginx
ss -ltn '( sport = :80 or sport = :443 )'
