# Reverse-Engineering the Goodix 27c6:5301 Sensor

This document details the reverse-engineering methodology used to analyze the **Goodix `27c6:5301`** sensor from vendor Windows driver packages and bring it to Linux.

---

## 1. Background & Driver Packages

Dell laptops with the `27c6:5301` sensor were supplied with two driver packages:
- `Goodix-Fingerprint-Sensor-Driver_35JWD_WIN64_2.1.32.200` (Legacy DUP)
- `Goodix-Fingerprint-Sensor-Driver_GR86V_WIN64_3.20.30.110` (Modern DUP)

Both packages were self-extracting zip archives containing .NET installers (`setup.exe`).

### 1.1. Analyzing 35JWD
Unpacking `setup.exe` yielded 4 embedded PE DLLs:
- `usbinterface.dll`: User-Mode Driver Framework (UMDF) USB driver.
- `WBDI_Data_Enclave.dll`: Intel SGX enclave containing encrypted matcher code.
- `EngineAdapter.dll`: Matcher adapter.
- `Fp_data_processor_Coating.dll`: Image pre-processing routines.

Inspection of `usbinterface.inf` revealed support only for `PID_5385` and `PID_5395`, indicating that 35JWD did not target 5301 directly.

### 1.2. Analyzing GR86V
Unpacking GR86V revealed modern TLS-PSK architecture (`PskUnify.c`, `FpMcuCmd.c`, `McuDevLoader.c`) for devices `PID538D` and `PID533C`. However, inspection of the configuration data table in `Wbdi.dll` revealed a 256-byte static configuration block:

```text
08 00 00 00 11 54 65 24 89 ab cd ef ...
```

This 256-byte sequence matched the configuration block extracted for `27c6:5201`.

---

## 2. Hardware Live Probing

Direct USB queries on real hardware confirmed:
- Chip ID register (`0x0000`) returned `0x2202a0`.
- Firmware query returned `GF3208_HT_APP_10035`.
- Interface layout was standard CDC-ACM modem with bulk data endpoints.

This proved that the **5301 uses the same generation of hardware and the identical "wrapless" protocol as the 5201**, rather than the newer TLS-encrypted protocol.

---

## 3. Resolving Hardware Discrepancies

While the core protocol is shared with the 5201, two critical hardware differences were discovered during live testing:

### 3.1. Reset Stray Packet
After sending the sensor reset command (`0xa2`), the 5301 MCU acknowledges with `0xb0` (ACK), but then transmits an asynchronous `0xa2` status packet into the IN endpoint. When the host immediately sent `0x90` (CONFIG), the driver expected an ACK for `0x90` but received the stray `0xa2`, resulting in SSM failure.

**Solution:** The driver transport loop was updated to allow skipping up to 12 valid but out-of-order stray packets.

### 3.2. Empty Sensor Noise Floor (Ridge Energy)
The driver verifies that the sensor is empty during activation by computing the band-pass ridge energy:
- On 5201: Empty sensor noise floor is ~15.
- On 5301: Empty sensor noise floor was measured at **25.05**.
- Hardcoded `GDX_RIDGE_EMPTY` in upstream 5201 driver: `25.0`.

Because `25.05 > 25.0`, the driver believed a finger was permanently resting on the sensor and refused to complete activation. Genuine finger touches measure **64.71**.

**Solution:** Adjusted `GDX_RIDGE_EMPTY` to **30.0** and `GDX_RIDGE_FINGER` to **42.0**. Activation and background acquisition now succeed immediately on the first attempt.
