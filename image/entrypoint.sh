#!/bin/bash
# Usage: lab-entry <auth|student|resolver|web>
set -e
role="$1"

# Point the container at the lab resolver instead of Docker's embedded DNS (127.0.0.11).
if [ -n "$RESOLVER" ]; then
  printf 'nameserver %s\n' "$RESOLVER" > /etc/resolv.conf
fi

# Artificial latency (root/TLD). Needs cap_add: NET_ADMIN and sch_netem on the host.
if [ -n "$NETEM_DELAY" ]; then
  tc qdisc replace dev eth0 root netem delay "$NETEM_DELAY" \
    || echo "WARNING: netem not applied (missing NET_ADMIN or sch_netem module)" >&2
fi

case "$role" in
  auth)
    exec named -f -u bind -c /lab/named.conf
    ;;
  student)
    named -u bind -c /lab/named.conf || echo "WARNING: named failed to start, see /var/log/named/named.log" >&2
    cd /lab/zone
    exec ttyd -W -p 7681 -c "$TTYD_CRED" -t titleFixed="$STUDENT_ID" bash -l
    ;;
  resolver)
    exec unbound -d -c /lab/unbound.conf
    ;;
  web)
    exec nginx -c /lab/nginx.conf -g 'daemon off;'
    ;;
  *)
    echo "unknown role: $role" >&2; exit 1
    ;;
esac
