#!/usr/bin/env python3
"""
Goodix 27c6:5301 standalone USB capture and protocol PoC tool.
Directly communicates with the sensor over USB bulk endpoints using libusb:
- Detaches CDC ACM kernel driver
- Drains stale TX queue messages
- Uploads 256-byte sensor RAM configuration
- Configures finger detection (FDT_MANUAL)
- Captures empty background frame
- Polls for finger touch and saves 12-bit raw PGM and 8-bit PNG images
"""

import os
import struct
import time
import zlib
import usb.core
import usb.util

VID, PID = 0x27C6, 0x5301
EP_OUT, EP_IN = 0x03, 0x81
W, H = 108, 88
PIXELS = W * H
IMG_BYTES = PIXELS * 3 // 2  # 12-bit packed: 14256 bytes

# 256-byte sensor configuration extracted from vendor driver
CONFIG = bytes([
    0x08, 0x00, 0x00, 0x00, 0x11, 0x54, 0x65, 0x24, 0x89, 0xab, 0xcd, 0xef,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x13, 0xba, 0x00, 0x01, 0x00, 0xca, 0x00, 0x07, 0x00, 0x84, 0x00, 0x80,
    0x81, 0x86, 0x00, 0x80, 0x85, 0x86, 0x00, 0x80, 0x82, 0x80, 0x00, 0x80,
    0x80, 0x80, 0x00, 0x80, 0x89, 0x80, 0x00, 0x80, 0x8a, 0x80, 0x00, 0x80,
    0x8b, 0x80, 0x00, 0x80, 0x8c, 0x80, 0x00, 0x80, 0x88, 0x80, 0x00, 0x80,
    0x83, 0x80, 0x00, 0x80, 0x87, 0x80, 0x00, 0x80, 0x80, 0x90, 0x80, 0x95,
    0x80, 0x94, 0x80, 0x93, 0x80, 0x83, 0x80, 0x87, 0x80, 0x8e, 0x80, 0x8f,
    0x80, 0x90, 0x80, 0x81, 0x80, 0x82, 0x80, 0x8a, 0x80, 0x89, 0x80, 0x8b,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00
])

ZERO2 = b"\x00\x00"
RESET_SENSOR = bytes([0x01, 20])
DRV_STATE = b"\x01\x00"
IMAGE_REQUEST = bytes([0x01, 0x00, 0x8b, 0x00, 0x84, 0x00, 0x8c, 0x00, 0x88, 0x00])
FDT_MANUAL = bytes([0x0d, 0x01, 0x8b, 0x00, 0x84, 0x00, 0x8c, 0x00, 0x88, 0x00,
                    0x80, 0x96, 0x80, 0x91, 0x80, 0x92, 0x80, 0x85, 0x80, 0x8c, 0x80, 0x86])


def checksum(data):
    return (0xAA - (sum(data) & 0xFF)) & 0xFF


def gea_decrypt(key, data):
    data = bytearray(data)
    for i in range(0, len(data) - 1, 2):
        u3 = (key >> 1) ^ key
        u2 = (((((((((key >> 0xF & 0x2000) | (key & 0x1000000)) >> 1 | (key & 0x20000)) >> 2
                   | (key & 0x1000)) >> 3 | ((key >> 7 ^ key) & 0x80000)) >> 1
                 | ((key >> 0xF ^ key) & 0x4000)) >> 2 | (key & 0x2000)) >> 2
               | (u3 & 0x40) | (key & 0x20)) >> 1
              | ((key >> 9 ^ (key << 8)) & 0x800) | (((key >> 0x14) ^ (key * 2)) & 4)
              | (((key * 8) ^ (key >> 0x10)) & 0x4000) | (((key >> 2) ^ (key >> 0x10)) & 0x80)
              | (((key << 6) ^ (key >> 7)) & 0x100) | ((key & 0x100) << 7))
        u1 = key & 0xFFFF
        key = (((key ^ ((u3 >> 0x14 ^ key) >> 10)) << 0x1F) | (key >> 1)) & 0xFFFFFFFF
        stream = ((u2 >> 8) & 0xFFFF) + (((u2 & 0xFF) | (u1 & 1)) * 0x100)
        word = (data[i] | (data[i + 1] << 8)) ^ stream
        data[i] = word & 0xFF
        data[i + 1] = (word >> 8) & 0xFF
    return bytes(data)


def crc32_mpeg2(data):
    crc = 0xFFFFFFFF
    for b in data:
        crc ^= b << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) if (crc & 0x80000000) else crc << 1
    return crc & 0xFFFFFFFF


def decode_u32(b):
    return b[0] * 0x100 + b[1] + b[2] * 0x1000000 + b[3] * 0x10000


def unpack_12bit(body):
    pixels = []
    for i in range(0, len(body), 6):
        c = body[i:i + 6]
        pixels.append(((c[0] & 0x0F) << 8) + c[1])
        pixels.append((c[3] << 4) + (c[0] >> 4))
        pixels.append(((c[5] & 0x0F) << 8) + c[2])
        pixels.append((c[4] << 4) + (c[5] >> 4))
    return pixels


def decode_frame(payload):
    header = payload[:5]
    raw_pixels = payload[5:5 + IMG_BYTES]
    crc_bytes = payload[5 + IMG_BYTES:5 + IMG_BYTES + 4]
    expected_crc = decode_u32(crc_bytes)
    actual_crc = crc32_mpeg2(raw_pixels)
    if actual_crc != expected_crc:
        raise ValueError(f"CRC mismatch: expected {expected_crc:#010x}, calculated {actual_crc:#010x}")
    decrypted = gea_decrypt(0x12345678, raw_pixels)
    return unpack_12bit(decrypted)


class Device:
    def __init__(self):
        self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        if self.dev is None:
            raise RuntimeError("Goodix 27c6:5301 not found. Is the udev rule installed?")
        try:
            self.dev.reset()
            time.sleep(0.5)
            self.dev = usb.core.find(idVendor=VID, idProduct=PID)
        except Exception:
            pass
        for intf in (0, 1):
            try:
                if self.dev.is_kernel_driver_active(intf):
                    self.dev.detach_kernel_driver(intf)
            except Exception:
                pass
        self.dev.set_configuration()
        usb.util.claim_interface(self.dev, 1)
        self.rx = bytearray()
        self.mid_msg = False

    def _send_msg(self, cmd, payload=b""):
        total_len = len(payload) + 1
        msg = bytes([cmd, total_len & 0xFF, (total_len >> 8) & 0xFF]) + payload
        msg += bytes([checksum(msg)])
        chunks = []
        c0 = msg[:64].ljust(64, b"\x00")
        chunks.append(c0)
        pos = 64
        while pos < len(msg):
            rem = msg[pos:pos + 63]
            c = bytes([cmd | 1]) + rem
            chunks.append(c.ljust(64, b"\x00"))
            pos += 63
        blob = b"".join(chunks)
        self.dev.write(EP_OUT, blob, timeout=3000)

    def _read_chunk(self, timeout):
        try:
            return bytes(self.dev.read(EP_IN, 64, timeout=timeout))
        except usb.core.USBTimeoutError:
            return None
        except usb.core.USBError as e:
            if "Operation timed out" in str(e):
                return None
            raise

    def _drain(self, rounds=4):
        """Flush stale messages left in USB buffer from previous sessions."""
        for r in range(rounds):
            try:
                self._send_msg(0x00, ZERO2)
            except Exception:
                pass
            t0 = time.time()
            while time.time() - t0 < 0.15:
                chunk = self._read_chunk(80)
                if chunk is None:
                    break
                if not chunk:
                    continue
        self.rx = bytearray()
        self.mid_msg = False

    def _read_msg(self, timeout=3000):
        self.rx = bytearray()
        self.mid_msg = False
        while True:
            chunk = self._read_chunk(timeout)
            if chunk is None:
                raise TimeoutError("Read timed out")
            if not chunk or all(b == 0 for b in chunk):
                continue
            if not self.mid_msg:
                if len(chunk) < 3:
                    raise RuntimeError("Short message header")
                self.rx += chunk
            else:
                if chunk[0] != (self.rx[0] | 1):
                    raise RuntimeError(f"Corrupted continuation chunk {chunk[0]:#02x}")
                self.rx += chunk[1:]
            self.mid_msg = True
            expected = 3 + (self.rx[1] | self.rx[2] << 8)
            if len(self.rx) >= expected:
                msg = bytes(self.rx[:expected])
                self.rx = self.rx[expected:]
                self.mid_msg = False
                payload = msg[3:]
                chk = (0xAA - sum(msg[:-1])) & 0xFF
                if payload[-1] != chk and payload[-1] != 0x88:
                    raise RuntimeError(f"Checksum mismatch: {payload[-1]:#x}")
                return msg[0], payload[:-1]

    def _cmd(self, c, payload=b"", want_reply=False, timeout=3000):
        self._send_msg(c, payload)
        mismatch = 0
        while True:
            cmd, rep = self._read_msg(timeout)
            if cmd == 0xB0:
                if rep[0] != c:
                    mismatch += 1
                    if mismatch > 12:
                        raise RuntimeError(f"Unmatched ACK: {rep[0]:#x}")
                    time.sleep(0.02)
                    continue
                break
            if want_reply and cmd == c:
                return rep
            mismatch += 1
            if mismatch > 12:
                raise RuntimeError(f"Stray message while awaiting ACK: {cmd:#x}")
            time.sleep(0.02)
        if not want_reply:
            return None
        mismatch = 0
        while True:
            cmd, rep = self._read_msg(timeout)
            if cmd == c:
                return rep
            mismatch += 1
            if mismatch > 12:
                raise RuntimeError(f"Unmatched reply: {cmd:#x}")
            time.sleep(0.02)

    def bring_up(self):
        print("[*] DRAIN: Flushing TX queue...")
        self._drain()
        print("[*] PING")
        self._cmd(0x00, ZERO2)
        print("[*] FIRMWARE")
        rep = self._cmd(0xA8, ZERO2, want_reply=True)
        fw = rep.split(b"\x00")[0].decode("latin1")
        print(f"    Firmware: {fw!r}")
        print("[*] RESET")
        self._cmd(0xA2, RESET_SENSOR)
        time.sleep(0.05)
        print("[*] CONFIG (256B)")
        rep = self._cmd(0x90, CONFIG, want_reply=True)
        ok = int.from_bytes(rep[:2], "little")
        if ok != 1:
            raise RuntimeError(f"Sensor rejected config: {ok}")
        print("    Config accepted")
        print("[*] DRV_STATE x2")
        self._cmd(0xC4, DRV_STATE)
        self._cmd(0xC4, DRV_STATE)
        print("[*] FDT_MANUAL")
        self._cmd(0x36, FDT_MANUAL, want_reply=True)

    def capture_frame(self, timeout=5000):
        self._send_msg(0x20, IMAGE_REQUEST)
        cmd, rep = self._read_msg(timeout)
        if cmd == 0x20:
            return decode_frame(rep)
        if cmd != 0xB0:
            raise RuntimeError(f"Expected ACK: {cmd:#x}")
        cmd, rep = self._read_msg(timeout)
        if cmd != 0x20:
            raise RuntimeError(f"Expected image: {cmd:#x}")
        return decode_frame(rep)

    def sleep(self):
        try:
            self._send_msg(0x60, b"\x01\x00")
            self._read_msg(500)
        except Exception:
            pass

    def close(self):
        try:
            usb.util.release_interface(self.dev, 1)
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def write_png(path, gray, w, h, scale=1):
    ww, hh = w * scale, h * scale
    raw = b""
    for y in range(hh):
        raw += b"\x00"
        for x in range(ww):
            raw += bytes([gray[y * w + x] if scale == 1 else gray[(y // scale) * w + x // scale]])

    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", ww, hh, 8, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main():
    with Device() as d:
        d.bring_up()
        print("[*] Acquiring empty sensor background frame...")
        bg = d.capture_frame()
        print(f"    Background: min={min(bg)} max={max(bg)}")
        print("[*] Place your finger on the sensor within 20 seconds...")
        frame = None
        deadline = time.time() + 20
        while time.time() < deadline:
            f = d.capture_frame()
            diff = sum(abs(a - b) for a, b in zip(f, bg)) / len(bg)
            if diff > 50:
                frame = f
                break
            time.sleep(0.15)
        d.sleep()
        if frame is None:
            raise SystemExit("Finger was not detected within timeout.")

    diff = [min(255, max(0, ((a - b + 2048) >> 4))) for a, b in zip(frame, bg)]
    write_png("fingerprint_raw.png", diff, W, H)
    write_png("fingerprint_4x.png", diff, W, H, scale=4)
    with open("fingerprint.pgm", "wb") as f:
        f.write(f"P5 {W} {H} 4095\n".encode())
        f.write(b"".join(v.to_bytes(2, "big") for v in frame))
    print("[+] Saved fingerprint_raw.png, fingerprint_4x.png, and fingerprint.pgm in current directory.")


if __name__ == "__main__":
    main()
