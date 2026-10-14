# FingerPrint-Sensor-Goodix-5301-linux

[![License: LGPL v2.1](https://img.shields.io/badge/License-LGPL_v2.1-blue.svg)](LICENSE)
[![Platform: Linux](https://img.shields.io/badge/Platform-Linux-orange.svg)]()
[![Hardware: Goodix 27c6:5301](https://img.shields.io/badge/Hardware-27c6%3A5301-green.svg)]()

Linux fingerprint driver (libfprint) for the **Goodix `27c6:5301`** (and `27c6:5201`) fingerprint reader, found in laptops such as the **Dell Inspiron 15 7577** and **ASUS ZenBook S UX391UA**.

This driver integrates with standard Linux **fprintd**, enabling biometric authentication for `sudo`, Polkit authorization dialogs, display managers (SDDM, GDM), and desktop lock screens (KDE Plasma 6, GNOME).

---

## Hardware Compatibility

Check your device ID with `lsusb`:

```bash
lsusb | grep 27c6:5301
```

```text
Bus 001 Device 005: ID 27c6:5301 Shenzhen Goodix Technology Co.,Ltd. Fingerprint Reader
```

Laptops confirmed working:
- **Dell Inspiron 15 7577** (and other Dell laptops equipped with `27c6:5301`)
- **ASUS ZenBook S UX391UA** (`27c6:5201`)

---

## Features

- **Standard fprintd Driver:** Works with native `fprintd-enroll` and `fprintd-verify`.
- **Desktop Environments:** Full support for KDE Plasma 6 (KScreenLocker), SDDM, GNOME Shell, GDM, and PAM.
- **Isolated Installation:** Installs to `/opt/libfprint-goodix5301/` with a systemd drop-in. Does not overwrite distribution packages or break package manager updates.
- **Minimal Runtime Dependencies:** Requires only ~20 MB of core runtime libraries (`libopencv-core410`, `libopencv-features2d410`, `libgusb2`). No heavy 1 GB development SDKs required.
- **Hardware Calibrated:**
  - Fixes USB autosuspend freeze (keeps sensor powered).
  - Blocks ModemManager AT probe interference on the CDC-ACM serial interface.
  - Handles asynchronous `0xa2` stray status packets after MCU reset.
  - Re-calibrated empty-sensor noise floor (`25.05`) to prevent false finger-present locks.

---

## Quick Install (Pre-built Binary)

The repository includes a pre-compiled 64-bit x86_64 library. To install:

```bash
git clone https://github.com/<username>/FingerPrint-Sensor-Goodix-5301-linux.git
cd FingerPrint-Sensor-Goodix-5301-linux
sudo ./install.sh
```

The installer will:
1. Ensure runtime packages (`fprintd`, `libpam-fprintd`, `libgusb2`, OpenCV runtime) are present.
2. Deploy the driver to `/opt/libfprint-goodix5301/lib/`.
3. Configure `fprintd` via a systemd drop-in to load this library.
4. Install udev rules and restart the service.

---

## Usage

### 1. Check Device Recognition
Run as your regular user (without `sudo`):

```bash
fprintd-list $USER
```
Expected output:
```text
found 1 devices
Device at /net/reactivated/Fprint/Device/0
Using device /net/reactivated/Fprint/Device/0
Fingerprints for user <username> on Goodix Fingerprint Sensor 27c6:5201/5301 (press):
```

### 2. Enroll a Finger
```bash
fprintd-enroll -f right-index-finger
```
Because the physical sensor is small (5 × 4 mm), the enrollment process requires **15 presses**. Press, hold for about a second, release, and slightly vary the angle and position between presses.

### 3. Verify
```bash
fprintd-verify
```
Touch the sensor. You should see `verify-match`.

### 4. Enable Authentication for Sudo and Lock Screen
To enable fingerprint authentication across PAM (login, lock screen, `sudo`):

```bash
sudo pam-auth-update
```
Use the arrow keys and spacebar to select:
`[*] Fingerprint authentication`  
Press `Tab` to select `<Ok>` and hit `Enter`.

---

## Uninstall

To remove the driver and restore distribution defaults:

```bash
sudo ./uninstall.sh
```

To delete all enrolled fingerprints:
```bash
fprintd-delete $USER
```

---

## Building from Source

If you prefer to compile from source:

```bash
sudo apt install -y git meson ninja-build gcc g++ libglib2.0-dev libusb-1.0-0-dev libgusb-dev libopencv-dev
./build_from_source.sh
sudo ./install.sh
```

---

## How It Works

1. **Protocol:** The sensor connects as a CDC-ACM modem, but exchanges Goodix "wrapless" binary packets over two USB bulk endpoints (Interface 1, EP `0x03` OUT / `0x81` IN).
2. **De-obfuscation:** Each 14,256-byte frame (108 × 88 pixels, 12-bit depth) is verified via CRC32/MPEG-2, de-obfuscated with Goodix's GEA stream cipher using key `0x12345678`, and unpacked into 12-bit grayscale pixels.
3. **Contrast & Cropping:** Edges are cropped to 104 × 84 pixels, background-subtracted against an empty sensor frame, and contrast-stretched to 8-bit.
4. **Matching:** Uses **SIGFM (MR !530)** with OpenCV SIFT keypoint matching. Minutiae matching (NBIS) is not viable on this sensor because its small size yields only 2–3 genuine minutiae. SIGFM provides reliable matching with scores > 400.

For in-depth details, see:
- [docs/PROTOCOL.md](docs/PROTOCOL.md)
- [docs/REVERSE-ENGINEERING.md](docs/REVERSE-ENGINEERING.md)

---

## Repository Structure

```text
├── bin/                 # Pre-built driver library (libfprint-2.so.2.0.0)
├── docs/                # Technical protocol and reverse-engineering docs
├── patches/             # Git patches applied to libfprint
├── tools/               # Standalone Python hardware PoC tool (capture5301.py)
├── udev/                # Power control & ModemManager udev rules
├── build_from_source.sh # Source build script
├── install.sh           # Automated installer
├── uninstall.sh         # Automated uninstaller
└── README.md
```

---

## Credits & Acknowledgments

- **Jodi U. H. (`goodix-5201-linux`):** Original reverse-engineering of the 5201 wrapless protocol and driver.
- **Goodix Fingerprint Linux Development group (`goodix-fp-dump`):** GEA cipher and configuration layout research.
- **Matthieu Charette, Natasha England-Elbro, Timur Mangliev, Yassine Oudjana:** SIGFM matcher and libfprint MR !530 integration.
- **libfprint and fprintd teams:** Upstream biometric framework.

---

## License

The driver and libfprint modifications are licensed under the [LGPL-2.1-or-later](LICENSE), matching libfprint.
