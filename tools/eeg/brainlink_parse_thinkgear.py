from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def iter_thinkgear_packets(data: bytes):
    """
    Parse NeuroSky ThinkGear packets from a byte stream.

    Packet format (common):
      0xAA 0xAA  PLEN  [PAYLOAD...PLEN bytes]  CHKSUM
    CHKSUM = 255 - (sum(payload) & 0xFF)
    """
    i = 0
    n = len(data)
    while i + 4 < n:
        # Find sync 0xAA 0xAA
        if data[i] != 0xAA or data[i + 1] != 0xAA:
            i += 1
            continue

        plen = data[i + 2]
        # Sanity
        if plen == 0 or plen > 170:
            i += 2
            continue

        end = i + 3 + plen  # end of payload (exclusive)
        if end >= n:
            break

        payload = data[i + 3 : end]
        chksum = data[end]

        calc = (sum(payload) & 0xFF)
        calc = 0xFF - calc

        if chksum != calc:
            # bad packet; resync by moving one byte
            i += 1
            continue

        yield payload
        i = end + 1


def decode_payload(payload: bytes):
    """
    Decode ThinkGear payload into a dict.
    Handles common codes:
      0x02 poorSignal (1 byte)
      0x04 attention (1 byte)
      0x05 meditation (1 byte)
      0x16 blinkStrength (1 byte)
      0x80 rawWave (2 bytes signed) length=2
      0x83 EEG power bands length=24 (8x3 bytes) [optional]
    """
    out = {}
    i = 0
    L = len(payload)

    def read_u24(b0, b1, b2):
        return (b0 << 16) | (b1 << 8) | b2

    while i < L:
        code = payload[i]
        i += 1

        # Extended codes (0x55) can appear; handle by skipping extension bytes
        while code == 0x55 and i < L:
            code = payload[i]
            i += 1

        if i >= L:
            break

        # Single-byte value codes
        if code in (0x02, 0x04, 0x05, 0x16):
            val = payload[i]
            i += 1
            if code == 0x02:
                out["poor_signal"] = val
            elif code == 0x04:
                out["attention"] = val
            elif code == 0x05:
                out["meditation"] = val
            elif code == 0x16:
                out["blink_strength"] = val
            continue

        # Multi-byte value codes use [len][data...]
        vlen = payload[i]
        i += 1
        if i + vlen > L:
            break
        v = payload[i : i + vlen]
        i += vlen

        if code == 0x80 and vlen == 2:
            raw = int.from_bytes(v, byteorder="big", signed=True)
            out["raw_eeg"] = raw
        elif code == 0x83 and vlen == 24:
            # 8 EEG bands, each 3 bytes
            bands = [
                "delta", "theta", "low_alpha", "high_alpha",
                "low_beta", "high_beta", "low_gamma", "mid_gamma"
            ]
            vals = []
            for k in range(8):
                vals.append(read_u24(v[3*k], v[3*k+1], v[3*k+2]))
            out["eeg_power"] = dict(zip(bands, vals))
        else:
            # keep unknown codes for debugging
            out.setdefault("unknown", []).append({"code": code, "len": vlen, "hex": v.hex()})

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", default="data/eeg_training/raw/brainlink_raw.bin")
    ap.add_argument("--out", default="data/eeg_training/raw/brainlink_decoded.jsonl")
    ap.add_argument("--max", type=int, default=0, help="max packets (0=all)")
    args = ap.parse_args()

    data = Path(args.infile).read_bytes()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_packets = 0
    n_with_raw = 0
    n_with_attn = 0
    n_with_blink = 0

    t0 = time.time()
    with open(out_path, "w") as f:
        for payload in iter_thinkgear_packets(data):
            rec = decode_payload(payload)
            rec["t"] = time.time()  # parse-time timestamp (OK for offline decode)
            f.write(json.dumps(rec) + "\n")

            n_packets += 1
            if "raw_eeg" in rec:
                n_with_raw += 1
            if "attention" in rec:
                n_with_attn += 1
            if "blink_strength" in rec:
                n_with_blink += 1

            if args.max and n_packets >= args.max:
                break

    dt = time.time() - t0
    print(f"[✓] decoded packets: {n_packets} in {dt:.2f}s -> {out_path}")
    print(f"    with raw_eeg: {n_with_raw}")
    print(f"    with attention: {n_with_attn}")
    print(f"    with blink_strength: {n_with_blink}")
    print(f"    first lines:")
    # print first 3 lines
    lines = out_path.read_text().splitlines()[:3]
    for line in lines:
        print("    ", line[:200])


if __name__ == "__main__":
    main()
