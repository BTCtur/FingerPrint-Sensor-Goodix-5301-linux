# Standalone Tools

This directory contains standalone Python verification tools for the Goodix 27c6:5301 fingerprint reader.

## `capture5301.py`

A standalone Python implementation of the Goodix "wrapless" USB protocol. It directly talks to the sensor over USB bulk endpoints using `pyusb` (`libusb` backend):

- Drains stale messages from previous sessions
- Sends PING and verifies firmware string
- Uploads the 256-byte sensor RAM configuration
- Enters finger detection mode (`FDT_MANUAL`)
- Captures an empty background frame
- Polls for finger touch and saves:
  - `fingerprint_raw.png` (8-bit contrast stretched)
  - `fingerprint_4x.png` (4x scaled)
  - `fingerprint.pgm` (Ham 12-bit raw PGM)

### Requirements

```bash
pip install pyusb
```
Ensure the udev rule (`../udev/70-goodix-5301.rules`) is installed and your user belongs to the `dialout` group:

```bash
sudo usermod -aG dialout $USER
```

### Running

```bash
python3 capture5301.py
```
