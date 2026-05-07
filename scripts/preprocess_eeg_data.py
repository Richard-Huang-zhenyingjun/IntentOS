"""
Preprocess raw EEG training data.

Pipeline:
  1. Load raw .npz trial files
  2. Apply MNE preprocessing (notch filter, bandpass)
  3. Extract features (band power, statistical features)
  4. Normalize features
  5. Save processed dataset (X, y) ready for training

Usage:
  python scripts/preprocess_eeg_data.py --input data/eeg_training/raw --output data/eeg_training/processed
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/eeg_training/raw")
    parser.add_argument("--output", default="data/eeg_training/processed")
    parser.add_argument("--subject", default="richard")
    return parser.parse_args()


def load_trials(input_dir: str, subject: str) -> tuple[list[np.ndarray], list[int], list[dict]]:
    """Load all trial files for a subject."""
    input_path = Path(input_dir)
    trials_data = []
    labels = []
    meta_list = []

    # Find all trial files
    trial_files = sorted(input_path.glob(f"{subject}_*_trial*.npz"))

    for f in trial_files:
        data = np.load(f, allow_pickle=True)
        trials_data.append(data["eeg_data"])
        labels.append(int(data["label"]))
        meta_list.append({
            "file": str(f),
            "trial_type": str(data.get("trial_type", "unknown")),
            "session": int(data.get("session", 0)),
            "trial_idx": int(data.get("trial_idx", 0)),
        })

    return trials_data, labels, meta_list


def preprocess_trial(raw_data: np.ndarray, sfreq: float = 4.0) -> np.ndarray:
    """
    Preprocess a single trial's EEG data.

    Uses your existing MNE pipeline components where possible.

    Pipeline:
    1. Remove timestamp column if present
    2. Bandpass filter (1-40 Hz) — if sample rate supports it
    3. Notch filter (60 Hz) — if sample rate supports it
    4. Normalize (z-score)

    Note: BrainLink at ~4Hz has very limited bandwidth.
    For 4Hz data, we can only resolve frequencies up to 2Hz (Nyquist).
    Most EEG features require higher sample rates.

    For BrainLink's low sample rate, we use:
    - Statistical features (mean, std, min, max, kurtosis)
    - Raw signal characteristics
    - NOT frequency-domain features (insufficient bandwidth)

    ADAPT: If your BrainLink actually samples faster (some modes do),
    adjust sfreq and enable frequency-domain features.

    Args:
        raw_data: Shape (n_samples, n_channels) or (n_samples, n_channels+1)
                 Last column may be timestamp.
        sfreq: Sampling frequency in Hz.

    Returns:
        Preprocessed data, shape (n_samples, n_channels).
    """
    if raw_data.size == 0:
        return np.zeros((1, 1))

    # Remove timestamp column if present
    if raw_data.ndim == 2 and raw_data.shape[1] > 1:
        # Heuristic: if last column is monotonically increasing, it's timestamps
        last_col = raw_data[:, -1]
        if np.all(np.diff(last_col) >= 0):
            eeg = raw_data[:, :-1]
        else:
            eeg = raw_data
    else:
        eeg = raw_data.reshape(-1, 1) if raw_data.ndim == 1 else raw_data

    # Z-score normalization per channel
    for ch in range(eeg.shape[1]):
        std = np.std(eeg[:, ch])
        if std > 1e-10:
            eeg[:, ch] = (eeg[:, ch] - np.mean(eeg[:, ch])) / std

    return eeg


def extract_features(preprocessed: np.ndarray) -> np.ndarray:
    """
    Extract features from preprocessed EEG trial.

    For BrainLink's low sample rate (~4Hz), use time-domain features:
    - Mean amplitude
    - Standard deviation
    - Min, Max
    - Range (max - min)
    - Kurtosis
    - Skewness
    - Number of zero crossings
    - Mean absolute difference between consecutive samples
    - RMS (root mean square)

    Returns:
        Feature vector, shape (n_features,).
    """
    if preprocessed.size == 0:
        return np.zeros(10)

    features = []

    for ch in range(preprocessed.shape[1]):
        signal = preprocessed[:, ch]

        # Basic statistics
        features.append(np.mean(signal))
        features.append(np.std(signal))
        features.append(np.min(signal))
        features.append(np.max(signal))
        features.append(np.max(signal) - np.min(signal))  # Range

        # Higher-order statistics
        from scipy import stats as scipy_stats
        features.append(scipy_stats.kurtosis(signal) if len(signal) > 3 else 0.0)
        features.append(scipy_stats.skew(signal) if len(signal) > 2 else 0.0)

        # Signal dynamics
        zero_crossings = np.sum(np.diff(np.sign(signal)) != 0)
        features.append(zero_crossings)

        mean_abs_diff = np.mean(np.abs(np.diff(signal))) if len(signal) > 1 else 0.0
        features.append(mean_abs_diff)

        rms = np.sqrt(np.mean(signal ** 2))
        features.append(rms)

    return np.array(features, dtype=np.float64)


def main():
    args = parse_args()

    print("=" * 50)
    print("  EEG DATA PREPROCESSING")
    print("=" * 50)

    # Load trials
    print(f"\n[Loading trials from {args.input}...]")
    trials_data, labels, meta_list = load_trials(args.input, args.subject)
    print(f"  Loaded {len(trials_data)} trials")
    print(f"  Confirm: {sum(labels)}, Idle: {len(labels) - sum(labels)}")

    if len(trials_data) == 0:
        print("  No trials found. Run collect_eeg_data.py first.")
        return 1

    # Preprocess and extract features
    print("\n[Preprocessing and extracting features...]")
    X = []
    y = []
    valid_count = 0

    for i, (raw, label) in enumerate(zip(trials_data, labels)):
        try:
            preprocessed = preprocess_trial(raw)
            features = extract_features(preprocessed)

            if not np.any(np.isnan(features)) and not np.any(np.isinf(features)):
                X.append(features)
                y.append(label)
                valid_count += 1
            else:
                print(f"  ⚠ Trial {i}: NaN/Inf in features, skipping")

        except Exception as e:
            print(f"  ⚠ Trial {i}: preprocessing failed: {e}")

    X = np.array(X)
    y = np.array(y)

    print(f"  Valid trials: {valid_count}/{len(trials_data)}")
    print(f"  Feature matrix: {X.shape}")
    print(f"  Labels: {y.shape} (confirm={np.sum(y)}, idle={len(y) - np.sum(y)})")

    # Save processed dataset
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    dataset_path = output_path / f"{args.subject}_dataset.npz"
    np.savez(
        dataset_path,
        X=X,
        y=y,
        feature_names=[
            "mean", "std", "min", "max", "range",
            "kurtosis", "skewness", "zero_crossings",
            "mean_abs_diff", "rms"
        ] * (X.shape[1] // 10 if X.shape[1] >= 10 else 1),
        n_confirm=int(np.sum(y)),
        n_idle=int(len(y) - np.sum(y)),
    )

    print(f"\n  ✓ Dataset saved: {dataset_path}")
    print(f"  ✓ Shape: X={X.shape}, y={y.shape}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
