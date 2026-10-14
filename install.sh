#!/usr/bin/env bash
# ==============================================================================
# Goodix 27c6:5301 / 27c6:5201 Linux Driver Installer
# ==============================================================================
# This script:
# 1. Installs minimal runtime libraries (~20 MB) if missing.
# 2. Deploys the pre-built driver to isolated /opt/libfprint-goodix5301/lib/.
# 3. Creates an isolated systemd drop-in for fprintd (preserves distro packages).
# 4. Installs udev rules (disables autosuspend and prevents ModemManager probes).
# 5. Reloads udev and restarts fprintd.service.
# ==============================================================================

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "[!] Error: Root privileges required. Please run with sudo:"
    echo "    sudo $0"
    exit 1
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$DIR/bin"
UDEV_DIR="$DIR/udev"
INSTALL_PREFIX="/opt/libfprint-goodix5301"
DROPIN_DIR="/etc/systemd/system/fprintd.service.d"
DROPIN_FILE="$DROPIN_DIR/goodix5301.conf"
UDEV_RULE_DST="/etc/udev/rules.d/70-goodix-5301.rules"

echo "=================================================================="
echo " Goodix 27c6:5301 / 27c6:5201 Driver Installer"
echo "=================================================================="

# 1. Check and install minimal runtime dependencies
echo "[1/6] Checking runtime dependencies..."
RUNTIME_PKGS=("fprintd" "libpam-fprintd" "libgusb2" "libopencv-core410" "libopencv-features2d410")
MISSING_PKGS=()

for pkg in "${RUNTIME_PKGS[@]}"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
        MISSING_PKGS+=("$pkg")
    fi
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    echo "    Installing missing runtime libraries: ${MISSING_PKGS[*]}..."
    apt-get update -qq
    apt-get install -y --no-install-recommends "${MISSING_PKGS[@]}"
else
    echo "    All runtime libraries are satisfied."
fi

# 2. Deploy binary library
echo "[2/6] Deploying driver to $INSTALL_PREFIX/lib..."
install -d "$INSTALL_PREFIX/lib"
install -m 0755 "$BIN_DIR/libfprint-2.so.2.0.0" "$INSTALL_PREFIX/lib/"
ln -sf "libfprint-2.so.2.0.0" "$INSTALL_PREFIX/lib/libfprint-2.so.2"
ln -sf "libfprint-2.so.2" "$INSTALL_PREFIX/lib/libfprint-2.so"

# 3. Create fprintd systemd drop-in
echo "[3/6] Configuring fprintd service environment..."
install -d "$DROPIN_DIR"
cat > "$DROPIN_FILE" << 'EOF'
# Isolated libfprint build for Goodix 27c6:5301 / 27c6:5201.
# Remove this file or run uninstall.sh to revert to distro package.
[Service]
Environment=LD_LIBRARY_PATH=/opt/libfprint-goodix5301/lib
EOF

# 4. Deploy udev rules
echo "[4/6] Installing udev rules to $UDEV_RULE_DST..."
install -m 0644 "$UDEV_DIR/70-goodix-5301.rules" "$UDEV_RULE_DST"
udevadm control --reload
udevadm trigger --subsystem-match=usb --attr-match=idVendor=27c6 2>/dev/null || true
udevadm trigger --subsystem-match=tty 2>/dev/null || true

# 5. Restart fprintd
echo "[5/6] Reloading systemd and restarting fprintd.service..."
systemctl daemon-reload
systemctl restart fprintd.service || true
sleep 1

# 6. Verify service status
echo "[6/6] Verifying service status..."
if systemctl is-active --quiet fprintd.service; then
    echo "    fprintd.service: ACTIVE"
else
    echo "    fprintd.service is ready (will auto-activate on first D-Bus call)."
fi

echo
echo "=================================================================="
echo " [✓] Installation completed successfully!"
echo "=================================================================="
echo "Next steps (run as your normal user, without sudo):"
echo
echo " 1. Verify device is recognized:"
echo "    fprintd-list \$USER"
echo
echo " 2. Enroll a finger (touch and release 15 times):"
echo "    fprintd-enroll -f right-index-finger"
echo
echo " 3. Verify match:"
echo "    fprintd-verify"
echo
echo " 4. Enable PAM authentication for lock screen & sudo:"
echo "    sudo pam-auth-update"
echo "    (Enable [*] Fingerprint authentication)"
echo "=================================================================="
