#!/usr/bin/env bash
# firewall-setup.sh — opt-in host firewall baseline using ufw.
#
# !! THIS SCRIPT IS OPT-IN.  It is NOT run by install.sh. !!
# Run it manually only after reading the rules below and confirming that
# your SSH access method is included.
#
# What it does:
#   - Resets ufw to a clean state.
#   - Allows SSH (port 22) — DO NOT remove this before running.
#   - Allows LAN access to HA (8123), MQTT (1883), and Z2M (8080)
#     from RFC1918 address ranges only.
#   - Denies all other inbound connections.
#   - Enables ufw logging (low) for blocked traffic.
#
# Rollback:
#   sudo ufw disable            # disable without removing rules
#   sudo ufw reset              # reset all rules and disable
#
# Customisation:
#   - Adjust LAN_CIDR to match your home network range.
#   - Add rules for additional services before the 'ufw enable' call.
#   - If you use a non-standard SSH port, update the SSH rule.
#
# Usage:
#   sudo ./scripts/security/firewall-setup.sh
#
# Requirements:
#   - ufw installed:  sudo apt-get install ufw
#   - Requires root.
set -euo pipefail

[[ ${EUID:-$(id -u)} -ne 0 ]] && echo "Run as root (sudo)" && exit 1

if ! command -v ufw >/dev/null 2>&1; then
  echo "ufw is not installed.  Run: sudo apt-get install -y ufw"
  exit 1
fi

# ---------------------------------------------------------------------------
# LAN_CIDR controls which source addresses are allowed to reach homeauto ports.
# The default covers the entire RFC1918 192.168.x.y range, which works for
# most home setups.  Narrow it to your actual subnet for stricter access:
#
#   Single subnet:  HOMEAUTO_LAN_CIDR=192.168.1.0/24
#   Entire 10.x:    HOMEAUTO_LAN_CIDR=10.0.0.0/8
#   All RFC1918:    HOMEAUTO_LAN_CIDR=192.168.0.0/16  (default)
#
# If you have IoT VLANs or multiple subnets, set the tightest CIDR that
# covers only your trusted devices, or add extra rules after this script runs.
# ---------------------------------------------------------------------------
LAN_CIDR="${HOMEAUTO_LAN_CIDR:-192.168.0.0/16}"

echo "Configuring ufw firewall baseline for homeauto stack."
echo "LAN CIDR: ${LAN_CIDR}"
echo ""
echo "WARNING: SSH (port 22) will be allowed.  Ensure you can reach this host"
echo "         via SSH on port 22 before continuing."
echo ""

# Reset to a clean state (disables ufw, removes all rules)
ufw --force reset

# Default policies
ufw default deny incoming
ufw default allow outgoing

# SSH — always allow so you don't lock yourself out
ufw allow 22/tcp comment 'SSH'

# Homeauto stack ports — LAN only
ufw allow from "${LAN_CIDR}" to any port 8123 proto tcp comment 'Home Assistant (LAN)'
ufw allow from "${LAN_CIDR}" to any port 1883 proto tcp comment 'Mosquitto MQTT (LAN)'
ufw allow from "${LAN_CIDR}" to any port 8080 proto tcp comment 'Zigbee2MQTT frontend (LAN)'

# Enable logging for blocked traffic (low = denied packets only)
ufw logging low

# Enable the firewall
ufw --force enable

echo ""
echo "Firewall configured.  Current rules:"
ufw status verbose
echo ""
echo "To disable: sudo ufw disable"
echo "To reset:   sudo ufw reset"
