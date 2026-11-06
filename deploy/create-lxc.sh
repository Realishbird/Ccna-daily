#!/usr/bin/env bash
# Run on the Proxmox VE HOST shell. Creates a small Debian 12 LXC and installs CCNA Daily in it.
# Override any setting, e.g.:  CTID=150 STORAGE=local-zfs BRIDGE=vmbr1 bash create-lxc.sh
set -euo pipefail

CTID="${CTID:-$(pvesh get /cluster/nextid)}"
HOSTNAME="${HOSTNAME_CT:-ccna-daily}"
STORAGE="${STORAGE:-local-lvm}"          # where the container disk lives
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"  # where templates are downloaded
BRIDGE="${BRIDGE:-vmbr0}"
DISK_GB="${DISK_GB:-4}"
MEMORY_MB="${MEMORY_MB:-512}"
CORES="${CORES:-1}"
IP="${IP:-dhcp}"                          # or e.g. 192.168.1.50/24 (then set GW)
GW="${GW:-}"
BRANCH="${CCNA_BRANCH:-main}"

command -v pct >/dev/null || { echo "Run this on the Proxmox host (pct not found)." >&2; exit 1; }

echo "==> Finding the Debian 12 template"
pveam update >/dev/null
TEMPLATE="$(pveam available --section system | awk '/debian-12-standard/ {print $2}' | sort -V | tail -1)"
[[ -n "$TEMPLATE" ]] || { echo "No debian-12-standard template found." >&2; exit 1; }
if ! pveam list "$TEMPLATE_STORAGE" | grep -q "$TEMPLATE"; then
  pveam download "$TEMPLATE_STORAGE" "$TEMPLATE"
fi

NET="name=eth0,bridge=$BRIDGE,ip=$IP"
[[ -n "$GW" ]] && NET="$NET,gw=$GW"

echo "==> Creating CT $CTID ($HOSTNAME)"
pct create "$CTID" "$TEMPLATE_STORAGE:vztmpl/$TEMPLATE" \
  --hostname "$HOSTNAME" \
  --cores "$CORES" --memory "$MEMORY_MB" --swap 256 \
  --rootfs "$STORAGE:$DISK_GB" \
  --net0 "$NET" \
  --unprivileged 1 --features nesting=1 \
  --onboot 1 \
  --timezone host

pct start "$CTID"
echo "==> Waiting for network"
for _ in $(seq 1 30); do
  if pct exec "$CTID" -- getent hosts github.com >/dev/null 2>&1; then break; fi
  sleep 2
done

echo "==> Installing CCNA Daily"
pct exec "$CTID" -- bash -c "apt-get update -qq && apt-get install -y -qq curl ca-certificates >/dev/null && \
  curl -fsSL https://raw.githubusercontent.com/Realishbird/ccna-daily/$BRANCH/deploy/install.sh -o /root/install.sh && \
  CCNA_BRANCH=$BRANCH bash /root/install.sh"

echo
echo "Done. Container $CTID. Update later with: pct exec $CTID -- bash /root/install.sh"
