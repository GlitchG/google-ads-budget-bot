#!/bin/bash
# Hermes watchdog (--no-agent): alert to Telegram only if a Google Ads bot is down.
# Empty stdout = all healthy = silent.
down=""
for s in delo-ads-bot olla-budget-bot agency-budget-bot; do
  systemctl is-active --quiet "$s" 2>/dev/null || down="$down $s"
done
if [ -n "$down" ]; then
  echo "⚠️ Google Ads боты НЕ работают:$down"
  echo "Проверь: systemctl status <name>  ·  journalctl -u <name> -n 50"
fi
