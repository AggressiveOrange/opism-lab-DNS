#!/bin/bash
# Start the stand and check it. Run from the dns-lab folder after every codespace (re)start.
set -e
cd "$(dirname "$0")"
C="docker compose -f stand/compose.yaml"
$C up -d
BR=br-$(docker network inspect dnslab_lab -f '{{.Id}}' | cut -c1-12)
# Docker-in-docker in Codespaces: a legacy iptables FORWARD DROP policy blocks traffic
# between containers; allow traffic inside the stand's bridge in both tables.
for IPT in iptables iptables-legacy; do
  command -v "$IPT" >/dev/null || continue
  sudo "$IPT" -C FORWARD -i "$BR" -o "$BR" -j ACCEPT 2>/dev/null \
    || sudo "$IPT" -I FORWARD 1 -i "$BR" -o "$BR" -j ACCEPT
done
python3 check.py --stand stand --smoke
