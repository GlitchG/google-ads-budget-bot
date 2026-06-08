#!/bin/bash
# Watchdog: prints an alert only if a bot service is down (empty output = healthy
# = silent). Edit SERVICES, then schedule it (cron / systemd timer) and pipe the
# output to your alert channel (Telegram, email, etc.).
SERVICES="google-ads-budget-bot"
down=""
for s in $SERVICES; do
  systemctl is-active --quiet "$s" 2>/dev/null || down="$down $s"
done
if [ -n "$down" ]; then
  echo "⚠️ Bot service(s) DOWN:$down"
  echo "Check: systemctl status <name>  ·  journalctl -u <name> -n 50"
fi
