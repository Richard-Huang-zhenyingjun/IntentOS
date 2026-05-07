import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import time
from src.input.eeg.brainlink_stream import ThinkGearStream

stream = ThinkGearStream(port="/dev/tty.BrainLink_Lite", baud=57600)
stream.connect()

n = 0
t0 = time.time()

print("[+] Reading 5 seconds of live EEG...")

while time.time() - t0 < 5:
    s = stream.read_sample(max_wait_s=0.5)
    if s and s.raw_eeg is not None:
        n += 1

dt = time.time() - t0
print(f"[✓] raw_eeg samples: {n} in {dt:.2f}s  -> {n/dt:.1f} Hz")

stream.close()
