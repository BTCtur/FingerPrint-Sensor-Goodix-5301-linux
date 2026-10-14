#!/usr/bin/env bash
# ==============================================================================
# Goodix 27c6:5301 / 27c6:5201 Linux Driver Uninstaller
# ==============================================================================

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "[!] Error: Root privileges required. Please run with sudo:"
    echo "    sudo $0"
    exit 1
fi

echo "=================================================================="
echo " Uninstalling Goodix 27c6:5301 / 27c6:5201 Driver..."
echo "=================================================================="

echo "[*] Removing fprintd drop-in configuration..."
rm -f /etc/systemd/system/fprintd.service.d/goodix5301.conf
rmdir --ignore-fail-on-non-empty /etc/systemd/system/fprintd.service.d 2>/dev/null || true

echo "[*] Removing driver files from /opt..."
rm -rf /opt/libfprint-goodix5301

echo "[*] Removing udev rules..."
rm -f /etc/udev/rules.d/70-goodix-5301.rules
udevadm control --reload || true
udevadm trigger 2>/dev/null || true

echo "[*] Restarting fprintd to restore distribution defaults..."
systemctl daemon-reload
systemctl restart fprintd.service || true

echo
echo "=================================================================="
echo " [✓] Driver successfully uninstalled."
echo " System reverted to standard distribution libfprint."
echo " To delete enrolled fingerprints: fprintd-delete \$USER"
echo "=================================================================="
