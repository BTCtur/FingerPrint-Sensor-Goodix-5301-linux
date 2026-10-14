#!/usr/bin/env bash
# ==============================================================================
# Build libfprint with Goodix 27c6:5301 Driver & SIGFM from source
# ==============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$ROOT/build_src"
OUTPUT_BIN="$ROOT/bin"

echo "=================================================================="
echo " Building Goodix 27c6:5301 libfprint driver from source"
echo "=================================================================="

# Check build dependencies
echo "[1/4] Checking build dependencies..."
REQUIRED_PKGS=("git" "meson" "ninja-build" "gcc" "g++" "libglib2.0-dev" "libusb-1.0-0-dev" "libgusb-dev" "libopencv-dev")
MISSING=()
for p in "${REQUIRED_PKGS[@]}"; do
    if ! dpkg -s "$p" >/dev/null 2>&1; then
        MISSING+=("$p")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "[!] Missing build dependencies: ${MISSING[*]}"
    echo "    Please install them with: sudo apt install -y ${MISSING[*]}"
    exit 1
fi

# Clone or update libfprint base (branch with SIGFM MR !530 + goodix5201)
if [ ! -d "$BUILD_DIR" ]; then
    echo "[2/4] Cloning libfprint source..."
    git clone --depth 1 -b libfprint https://github.com/J0UH/goodix-5201-linux.git "$BUILD_DIR"
fi

cd "$BUILD_DIR"

# Apply patches
echo "[3/4] Applying 27c6:5301 patches..."
for patch in "$ROOT"/patches/*.patch; do
    echo "    Applying $(basename "$patch")..."
    git apply --check "$patch" 2>/dev/null && git apply "$patch" || echo "    (Already applied or skipped)"
done

# Meson configure and build
echo "[4/4] Compiling libfprint..."
if [ ! -d build ]; then
    meson setup build \
        --prefix=/opt/libfprint-goodix5301 \
        --libdir=lib \
        --buildtype=release \
        -Ddrivers=goodix5201 \
        -Ddoc=false \
        -Dgtk-examples=false \
        -Dintrospection=false \
        -Dinstalled-tests=false \
        -Dudev_rules=disabled \
        -Dudev_hwdb=disabled
fi

ninja -C build

# Copy built binary to bin/
mkdir -p "$OUTPUT_BIN"
cp -a build/libfprint/libfprint-2.so.2.0.0 "$OUTPUT_BIN/"
ln -sf libfprint-2.so.2.0.0 "$OUTPUT_BIN/libfprint-2.so.2"
ln -sf libfprint-2.so.2 "$OUTPUT_BIN/libfprint-2.so"

echo
echo "=================================================================="
echo " [✓] Build completed successfully!"
echo " Binary output: $OUTPUT_BIN/libfprint-2.so.2.0.0"
echo " Run 'sudo ./install.sh' to deploy."
echo "=================================================================="
