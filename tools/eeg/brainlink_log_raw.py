import argparse
import time
from pathlib import Path

import serial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/tty.BrainLink_Lite")
    ap.add_argument("--baud", type=int, default=57600)
    ap.add_argument("--out", default="data/eeg_training/raw/brainlink_raw.bin")
    ap.add_argument("--seconds", type=int, default=30)
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[+] Opening {args.port} @ {args.baud} baud")
    ser = serial.Serial(args.port, args.baud, timeout=1)

    t0 = time.time()
    total = 0

    print(f"[+] Logging raw bytes for {args.seconds}s -> {out_path}")
    with open(out_path, "wb") as f:
        while time.time() - t0 < args.seconds:
            chunk = ser.read(1024)
            if chunk:
                f.write(chunk)
                total += len(chunk)

    ser.close()
    print(f"[✓] Done. Wrote {total} bytes to {out_path}")


if __name__ == "__main__":
  main()
