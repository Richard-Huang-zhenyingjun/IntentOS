#!/usr/bin/env python3
"""
EEG Classifier Training.

Trains a binary CONFIRM/IDLE classifier on the preprocessed dataset.
Evaluates with stratified cross-validation to avoid optimistic single-split
results. Saves the best model to models/eeg_classifier.pkl.

Target accuracy: >= 70% (chance = 50%).
If < 70%: collect more data, check signal quality, tune features.

Usage:
    python scripts/train_eeg_classifier.py
    python scripts/train_eeg_classifier.py --min-accuracy 0.70
"""
from __future__ import annotations

import argparse
import csv
import pickle
import sys
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent.parent))


CANDIDATE_MODELS = {
    "logistic_regression": Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(C=1.0, max_iter=1000, class_weight="balanced")),
        ]
    ),
    "random_forest": Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                RandomForestClassifier(
                    n_estimators=100,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    ),
}


def train(dataset_path: str, output_path: str, min_accuracy: float) -> int:
    X, y = _load_dataset(dataset_path)
    _validate_dataset(X, y)

    print(f"Dataset: {len(X)} windows, {X.shape[1]} features")
    print(f"Classes: {dict(zip(*np.unique(y, return_counts=True)))}")

    results = {}
    n_splits = _choose_cv_splits(y)
    for name, model in CANDIDATE_MODELS.items():
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        scores = cross_val_score(model, X, y, cv=cv, scoring="balanced_accuracy")
        mean_acc = float(scores.mean())
        results[name] = (mean_acc, float(scores.std()), model)
        print(f"  {name:25s}: {mean_acc:.3f} +/- {scores.std():.3f} balanced accuracy")

    best_name, (best_acc, _, best_model) = max(results.items(), key=lambda item: item[1][0])
    print(f"\nBest model: {best_name} ({best_acc:.3f})")

    if best_acc < min_accuracy:
        print(f"\nWARNING: Accuracy {best_acc:.3f} < minimum {min_accuracy:.3f}")
        print("Do not deploy. Collect more data or improve signal quality.")
        print("Guidelines:")
        print("  - Need >= 200 total trials for reliable results")
        print("  - Check mean quality in dataset_report.txt (target > 0.7)")
        print("  - Try collecting in a quieter environment")
        print("  - Ensure consistent electrode placement each session")
        return 1

    best_model.fit(X, y)

    y_pred = best_model.predict(X)
    labels = ["IDLE", "CONFIRM"]
    print("\nFull-dataset classification report:")
    print(classification_report(y, y_pred, labels=labels, target_names=labels, zero_division=0))
    print("Confusion matrix (rows=true, cols=predicted):")
    print(confusion_matrix(y, y_pred, labels=labels))

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        pickle.dump(best_model, f)

    meta_path = out.with_suffix(".pkl.meta.txt") if out.suffix == ".pkl" else out.with_suffix(".meta.txt")
    _write_metadata(
        meta_path=meta_path,
        model_name=best_name,
        accuracy=best_acc,
        n_samples=len(X),
        n_features=X.shape[1],
        classes=np.unique(y),
        results=results,
    )

    print(f"\nOK Model saved -> {out}")
    print(f"OK Metadata -> {meta_path}")
    print("\nThis model replaces models/eeg_classifier.pkl.")
    print("Run smoke tests to verify end-to-end with real model:")
    print("  pytest tests/integration/test_phase2a_smoke.py -v -k invariant")
    return 0


def _load_dataset(path: str) -> tuple[np.ndarray, np.ndarray]:
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    X, y = [], []
    with dataset_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"Dataset has no header: {dataset_path}")
        feature_keys = [key for key in reader.fieldnames if key.startswith("f")]
        if not feature_keys:
            raise ValueError("Dataset has no feature columns named f0, f1, ...")
        if "label" not in reader.fieldnames:
            raise ValueError("Dataset missing required label column")

        for row in reader:
            X.append([float(row[key]) for key in feature_keys])
            y.append(row["label"].strip().upper())

    return np.array(X, dtype=np.float32), np.array(y)


def _validate_dataset(X: np.ndarray, y: np.ndarray) -> None:
    if len(X) == 0:
        raise ValueError("Dataset is empty")

    classes, counts = np.unique(y, return_counts=True)
    class_counts = dict(zip(classes, counts))
    missing = {"CONFIRM", "IDLE"} - set(classes)
    if missing:
        raise ValueError(f"Dataset missing class(es): {sorted(missing)}")

    if len(X) < 80:
        raise ValueError(f"Need at least 80 windows for training, found {len(X)}")

    too_small = {label: count for label, count in class_counts.items() if count < 40}
    if too_small:
        raise ValueError(f"Need at least 40 windows per class, found {too_small}")


def _choose_cv_splits(y: np.ndarray) -> int:
    _, counts = np.unique(y, return_counts=True)
    min_class_count = int(np.min(counts))
    return max(2, min(5, min_class_count))


def _write_metadata(
    meta_path: Path,
    model_name: str,
    accuracy: float,
    n_samples: int,
    n_features: int,
    classes: np.ndarray,
    results: dict,
) -> None:
    with meta_path.open("w", encoding="utf-8") as f:
        f.write(f"Model: {model_name}\n")
        f.write(f"CV balanced accuracy: {accuracy:.4f}\n")
        f.write("Candidate models:\n")
        for name, (mean_acc, std_acc, _) in results.items():
            f.write(f"  {name}: {mean_acc:.4f} +/- {std_acc:.4f}\n")
        f.write(f"Training samples: {n_samples}\n")
        f.write(f"Feature dimension: {n_features}\n")
        f.write(f"Classes: {[str(cls) for cls in classes]}\n")
        f.write("Feature extractor: src.input.eeg.features.extract_features\n")
        f.write("(Must match runtime decoder exactly. Re-train if features.py changes.)\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="data/eeg_training/processed/dataset.csv")
    parser.add_argument("--output", default="models/eeg_classifier.pkl")
    parser.add_argument("--min-accuracy", type=float, default=0.70)
    args = parser.parse_args()
    try:
        return train(args.dataset, args.output, args.min_accuracy)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
