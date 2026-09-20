#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y nginx

install -d -m 750 /etc/nginx/ssl/chatbot.iek.local
install -m 600 /tmp/cert.key /etc/nginx/ssl/chatbot.iek.local/private.key

openssl pkcs7 -print_certs -in /tmp/certnew.p7b -out /tmp/chatbot-certs.txt
awk '
    BEGIN { n = 0 }
    /BEGIN CERTIFICATE/ { n++; file = sprintf("/tmp/chatbot-cert-%d.pem", n) }
    n { print > file }
' /tmp/chatbot-certs.txt
cat /tmp/chatbot-cert-1.pem /tmp/chatbot-cert-2.pem > /etc/nginx/ssl/chatbot.iek.local/fullchain.pem
chmod 644 /etc/nginx/ssl/chatbot.iek.local/fullchain.pem

install -m 644 /tmp/iek-l0-ui.service /etc/systemd/system/iek-l0-ui.service
install -m 644 /tmp/iek-l1-ui.service /etc/systemd/system/iek-l1-ui.service
install -m 644 /tmp/nginx-chatbot-ui.conf /etc/nginx/sites-available/chatbot-ui
ln -sfn /etc/nginx/sites-available/chatbot-ui /etc/nginx/sites-enabled/chatbot-ui
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl daemon-reload
systemctl restart iek-l0-ui iek-l1-ui
systemctl enable --now nginx
ufw allow 80/tcp
ufw allow 443/tcp

rm -f /tmp/cert.key /tmp/certnew.p7b /tmp/chatbot-certs.txt /tmp/chatbot-cert-*.pem
