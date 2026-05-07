#!/usr/bin/env python3
"""
EEG Preprocessing Pipeline.

Reads raw session CSVs -> extracts features -> outputs labeled dataset.

Feature extraction uses src.input.eeg.features.extract_features exactly -
the same function used at inference time. This guarantees training/inference
feature parity.

Usage:
    python scripts/preprocess_eeg.py
    python scripts/preprocess_eeg.py --raw-dir data/eeg_training/raw --window-s 2.0

Output:
    data/eeg_training/processed/dataset.csv
    data/eeg_training/processed/dataset_report.txt
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.input.eeg.features import FEATURE_VECTOR_FIELDS, extract_features
from src.input.eeg.types import EEGSample


def preprocess(raw_dir: str, output_dir: str, window_s: float, sample_rate_hz: float) -> int:
    raw_path = Path(raw_dir)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    window_samples = max(1, int(window_s * sample_rate_hz))
    all_rows = []
    stats = defaultdict(int)

    session_files = sorted(raw_path.glob("session_*.csv"))
    if not session_files:
        print(f"No session files found in {raw_path}")
        return 1

    for session_file in session_files:
        print(f"Processing {session_file.name}...")
        rows = _process_session(session_file, window_samples)
        all_rows.extend(rows)
        for _, label, _ in rows:
            stats[label] += 1

    if not all_rows:
        print("No valid windows extracted. Check raw data quality.")
        return 1

    dataset_path = out_path / "dataset.csv"
    feature_dim = len(all_rows[0][0])
    headers = [f"f{i}" for i in range(feature_dim)] + ["label", "quality"]

    with dataset_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for feat_vec, label, quality in all_rows:
            writer.writerow([f"{float(v):.10g}" for v in feat_vec] + [label, f"{quality:.6f}"])

    report_path = out_path / "dataset_report.txt"
    _write_report(
        report_path=report_path,
        stats=stats,
        all_rows=all_rows,
        feature_dim=feature_dim,
        window_s=window_s,
        window_samples=window_samples,
        sample_rate_hz=sample_rate_hz,
    )

    print(f"\nDataset written -> {dataset_path}")
    print(f"Report -> {report_path}")
    _print_report(stats, all_rows)
    return 0


def _process_session(session_file: Path, window_samples: int):
    """Extract feature windows from one session CSV. Uses canonical extract_features."""
    rows = []
    samples_by_label = defaultdict(list)

    with session_file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"timestamp_ms", "value"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            missing = ", ".join(sorted(required - set(reader.fieldnames or [])))
            raise ValueError(f"{session_file} missing required column(s): {missing}")

        for row in reader:
            quality = float(row.get("quality") or row.get("valid") or 1.0)
            label = (row.get("label") or "IDLE").strip().upper()
            sample = EEGSample(
                timestamp_ms=float(row["timestamp_ms"]),
                value=float(row["value"]),
                quality=quality,
                label=label,
            )
            samples_by_label[label].append((sample, quality))

    for label, sample_quality_pairs in samples_by_label.items():
        samples = [sample for sample, _ in sample_quality_pairs]
        qualities = [quality for _, quality in sample_quality_pairs]

        stride = max(1, window_samples // 2)
        for start in range(0, max(1, len(samples) - window_samples + 1), stride):
            window = samples[start:start + window_samples]
            if len(window) < window_samples:
                continue
            feat_vec = extract_features(window)
            mean_quality = float(np.mean(qualities[start:start + window_samples]))
            rows.append((feat_vec, label, mean_quality))

    return rows


def _write_report(
    report_path: Path,
    stats,
    all_rows,
    feature_dim: int,
    window_s: float,
    window_samples: int,
    sample_rate_hz: float,
) -> None:
    total = sum(stats.values())
    qualities = [quality for _, _, quality in all_rows]

    with report_path.open("w", encoding="utf-8") as f:
        f.write(f"Total windows: {total}\n")
        for label in sorted(stats):
            count = stats[label]
            f.write(f"  {label}: {count} ({100 * count / total:.1f}%)\n")
        f.write(f"Mean quality: {np.mean(qualities):.3f}\n")
        f.write(f"Min quality:  {np.min(qualities):.3f}\n")
        f.write(f"Feature dimension: {feature_dim}\n")
        f.write(f"Feature fields: {', '.join(FEATURE_VECTOR_FIELDS)}\n")
        f.write(f"Window size: {window_s}s ({window_samples} samples @ {sample_rate_hz}Hz)\n")
        f.write("\nFeature extractor: src.input.eeg.features.extract_features\n")
        f.write("(Must match runtime decoder exactly)\n")


def _print_report(stats, all_rows) -> None:
    total = sum(stats.values())
    print("\nClass balance:")
    for label in sorted(stats):
        count = stats[label]
        bar = "#" * (count * 40 // total)
        print(f"  {label:8s} {count:4d} ({100 * count / total:.0f}%) {bar}")
    qualities = [quality for _, _, quality in all_rows]
    print(
        f"Mean quality: {np.mean(qualities):.3f} "
        f"(>70% = good, 50%-70% = acceptable)"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="data/eeg_training/raw")
    parser.add_argument("--output-dir", default="data/eeg_training/processed")
    parser.add_argument("--window-s", type=float, default=2.0)
    parser.add_argument("--sample-rate-hz", type=float, default=4.0)
    args = parser.parse_args()
    return preprocess(args.raw_dir, args.output_dir, args.window_s, args.sample_rate_hz)


if __name__ == "__main__":
    raise SystemExit(main())
