"""
Generate synthetic EEG fixture for CI testing.

Creates a CSV with known properties:
- 10 seconds of simulated single-channel EEG
- 3 deliberate "blink" events (double spikes) at known timestamps
- Background alpha rhythm + noise
- One dropout gap
"""
import csv
import numpy as np
from pathlib import Path


def generate_fixture(
    output_path: str = "tests/fixtures/eeg/synthetic_session.csv",
    duration_sec: float = 10.0,
    sfreq: float = 512.0,
    seed: int = 42,
):
    rng = np.random.RandomState(seed)
    
    n_samples = int(duration_sec * sfreq)
    timestamps = np.arange(n_samples) / sfreq * 1000  # ms
    
    # Base signal: alpha rhythm (10 Hz) + noise
    t = np.arange(n_samples) / sfreq
    alpha = 20 * np.sin(2 * np.pi * 10 * t)   # 10 Hz alpha
    noise = rng.normal(0, 5, n_samples)         # Background noise
    line_noise = 3 * np.sin(2 * np.pi * 60 * t)  # 60 Hz line noise
    
    signal = alpha + noise + line_noise
    
    # Add deliberate blink events (double spikes)
    blink_times_sec = [2.0, 5.0, 8.0]  # Known timestamps
    for bt in blink_times_sec:
        idx = int(bt * sfreq)
        # Double blink: two spikes ~200ms apart
        if idx + int(0.2 * sfreq) < n_samples:
            signal[idx] += 200       # First spike
            signal[idx + 1] += 150
            idx2 = idx + int(0.2 * sfreq)
            signal[idx2] += 180      # Second spike
            signal[idx2 + 1] += 130
    
    # Add one dropout gap (0.5s of zeros) at t=6.5s
    dropout_start = int(6.5 * sfreq)
    dropout_end = int(7.0 * sfreq)
    signal[dropout_start:dropout_end] = 0
    
    # Write CSV
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_ms', 'value', 'channel', 'valid'])
        
        for i in range(n_samples):
            valid = 1
            if dropout_start <= i < dropout_end:
                valid = 0  # Mark dropout samples
            
            writer.writerow([
                f"{timestamps[i]:.3f}",
                f"{signal[i]:.6f}",
                0,
                valid,
            ])
    
    # Write expected events
    events_path = output.parent / "synthetic_session_events.json"
    import json
    events = {
        'duration_sec': duration_sec,
        'sfreq': sfreq,
        'n_samples': n_samples,
        'blink_times_sec': blink_times_sec,
        'dropout_range_sec': [6.5, 7.0],
        'expected_min_confirms': 2,  # At least 2 of 3 blinks should be detected
    }
    with open(events_path, 'w') as f:
        json.dump(events, f, indent=2)
    
    print(f"Generated fixture: {output} ({n_samples} samples, {duration_sec}s)")
    print(f"Blink events at: {blink_times_sec}")
    print(f"Dropout at: 6.5-7.0s")


if __name__ == '__main__':
    generate_fixture()


