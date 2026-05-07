#!/usr/bin/env python3
"""
scripts/collect_eeg_data.py - Hardened EEG Training Data Collection Script

FIXES APPLIED:
  1. Format: writes CSV (not .npz) - matches ReplayDevice / synthetic_session.csv format
  2. EEGSample fields: reads .value, .timestamp_ms, .channel, .valid
  3. BrainLink extras: logs signal_quality, attention, meditation, blink strength per trial
  4. Crash safety: session manifest written per-trial, not only at session end
  5. Per-trial metadata: sample count, mean quality, timing, blink strength logged per trial

CSV output format:
    timestamp_ms,value,channel,valid,label,trial_id

Matches synthetic_session.csv column contract and adds label + trial_id columns.
ReplayDevice can read output files directly because timestamp_ms/value are unchanged.

Usage:
    python scripts/collect_eeg_data.py --sessions 4 --label-mode blink
    python scripts/collect_eeg_data.py --sessions 2 --dry-run    # no hardware needed
    python scripts/collect_eeg_data.py --sessions 1 --resume     # append to existing session
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Optional

# Project root on path.
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


TRIAL_PROTOCOL = {
    "rest_s": 3.0,
    "cue_s": 0.5,
    "action_s": 2.0,
    "post_rest_s": 2.0,
}
BASELINE_S = 30.0
TRIALS_PER_SESSION = 25
MIN_SAMPLES_PER_TRIAL = 2
QUALITY_WARN_THRESHOLD = 0.5
POLL_INTERVAL_S = 0.002
DRY_RUN_SAMPLE_HZ = 4.0


class TrialCSVWriter:
    """
    Writes EEGSample rows to CSV immediately after each trial (crash-safe).
    Output format matches synthetic_session.csv + label + trial_id columns.
    """

    HEADERS = ["timestamp_ms", "value", "channel", "valid", "label", "trial_id"]

    def __init__(self, path: Path, append: bool = False):
        self._path = path
        mode = "a" if append else "w"
        self._file = open(path, mode, newline="", buffering=1, encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.HEADERS)
        if not append:
            self._writer.writeheader()
            self._file.flush()
            os.fsync(self._file.fileno())

    def write_trial(self, samples: list[object], label: str, trial_id: str) -> int:
        """Write all samples from one trial. Flushes immediately."""
        count = 0
        for sample in samples:
            self._writer.writerow(
                {
                    "timestamp_ms": f"{sample.timestamp_ms:.3f}",
                    "value": f"{sample.value:.6f}",
                    "channel": sample.channel,
                    "valid": 1 if sample.valid else 0,
                    "label": label,
                    "trial_id": trial_id,
                }
            )
            count += 1
        self._file.flush()
        os.fsync(self._file.fileno())
        return count

    def close(self) -> None:
        self._file.close()


class _DryRunDevice:
    """Mimics BrainLinkDevice for --dry-run mode. Returns synthetic samples."""

    def __init__(self):
        self._rng = random.Random(42)
        self._t0 = time.time()

    def is_connected(self) -> bool:
        return True

    def get_device_stats(self) -> dict:
        return {
            "signal_quality": self._rng.randint(0, 50),
            "attention": self._rng.randint(40, 80),
            "meditation": self._rng.randint(40, 70),
        }

    @property
    def sample_rate_hz(self) -> float:
        return 4.0

    def read_sample(self) -> "_DryRunSample":
        elapsed_s = time.time() - self._t0
        return _DryRunSample(self._rng, elapsed_s * 1000.0)

    def disconnect(self) -> None:
        pass


class _DryRunSample:
    def __init__(self, rng: random.Random, t_ms: float):
        self.timestamp_ms = t_ms
        self.value = rng.gauss(0, 15.0)
        self.channel = 0
        self.valid = True
        self.quality = 1.0
        self.metadata = {}


@dataclass
class TrialRecord:
    """Per-trial metadata written to manifest immediately after each trial."""
    trial_id: str
    label: str
    sample_count: int
    mean_value: float
    min_value: float
    max_value: float
    valid_sample_rate: float
    timing_start_ms: float
    timing_end_ms: float
    duration_actual_s: float
    device_signal_quality: Optional[int] = None
    device_attention: Optional[int] = None
    device_meditation: Optional[int] = None
    warning: Optional[str] = None


class SessionManifest:
    """
    JSON manifest written per-trial so a crash never loses session-level metadata.
    Lives alongside the CSV: session_YYYYMMDD_HHMMSS.manifest.json
    """

    def __init__(
        self,
        path: Path,
        session_id: str,
        label_mode: str,
        dry_run: bool,
        sample_rate_hz: float,
        existing: Optional[dict] = None,
    ):
        self._path = path
        self._data = existing or {
            "session_id": session_id,
            "label_mode": label_mode,
            "dry_run": dry_run,
            "sample_rate_hz": sample_rate_hz,
            "protocol": TRIAL_PROTOCOL,
            "baseline_s": BASELINE_S,
            "trials_planned": TRIALS_PER_SESSION,
            "trials_complete": 0,
            "trials": [],
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
        }
        self._flush()

    @classmethod
    def resume(cls, path: Path) -> Optional["SessionManifest"]:
        data = _read_json(path)
        if not data:
            return None
        return cls(
            path=path,
            session_id=data["session_id"],
            label_mode=data.get("label_mode", "blink"),
            dry_run=bool(data.get("dry_run", False)),
            sample_rate_hz=float(data.get("sample_rate_hz", 0.0)),
            existing=data,
        )

    @property
    def data(self) -> dict:
        return self._data

    @property
    def session_id(self) -> str:
        return str(self._data["session_id"])

    @property
    def trials(self) -> list[dict]:
        return self._data.setdefault("trials", [])

    def set_baseline(self, baseline: dict) -> None:
        self._data["baseline"] = baseline
        self._flush()

    def record_trial(self, trial: TrialRecord) -> None:
        """Called immediately after each trial. Persists to disk."""
        self._data["trials_complete"] = int(self._data.get("trials_complete", 0)) + 1
        self.trials.append(asdict(trial))
        self._flush()

    def close(self) -> None:
        self._data["completed_at"] = datetime.now().isoformat()
        self._flush()
        logger.info("Manifest closed -> %s", self._path)

    def _flush(self) -> None:
        tmp = self._path.with_suffix(".tmp.json")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        tmp.replace(self._path)


def run_collection(
    sessions: int,
    dry_run: bool,
    label_mode: str,
    output_dir: str,
) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if dry_run:
        device = _DryRunDevice()
        print("[DRY RUN] No hardware - synthetic samples, real timing.")
    else:
        from src.input.eeg.device_brainlink import BrainLinkDevice

        device = BrainLinkDevice()
        device.connect()
        if not _is_connected(device):
            print("ERROR: BrainLink not connected. Check Bluetooth pairing.")
            return 1
        print(f"BrainLink connected. Sample rate: {device.sample_rate_hz:.1f} Hz")

    sample_buffer: list = []

    def _on_sample(sample) -> None:
        sample_buffer.append(sample)

    callback_mode = False
    if not dry_run:
        callback_mode = _start_callback_stream(device, _on_sample)

    try:
        for session_num in range(1, sessions + 1):
            csv_path = _run_session(
                session_num=session_num,
                device=device,
                sample_buffer=sample_buffer,
                out_dir=out,
                label_mode=label_mode,
                dry_run=dry_run,
                callback_mode=callback_mode,
            )
            print(f"\nOK Session {session_num}/{sessions} complete -> {csv_path}")
            if session_num < sessions:
                print("\nRest 5 minutes. Press Enter when ready for next session.")
                input()
    finally:
        if not dry_run:
            if hasattr(device, "stop"):
                device.stop()
            device.disconnect()

    print("\nCollection done.")
    print(f"Next step: python scripts/preprocess_eeg.py --raw-dir {out}")
    return 0


def _is_connected(device) -> bool:
    value = getattr(device, "is_connected", False)
    return bool(value() if callable(value) else value)


def _start_callback_stream(device, callback) -> bool:
    if not (hasattr(device, "set_callback") and hasattr(device, "start")):
        return False
    device.set_callback(callback)
    device.start()
    return True


def _device_sample_rate(device, dry_run: bool) -> float:
    return float(getattr(device, "sample_rate_hz", 0.0) or 0.0)


def _run_session(
    session_num: int,
    device,
    sample_buffer: list,
    out_dir: Path,
    label_mode: str,
    dry_run: bool,
    callback_mode: bool = False,
) -> Path:
    session_id = f"session_{session_num:03d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    csv_path = out_dir / f"{session_id}.csv"
    manifest_path = out_dir / f"{session_id}.manifest.json"
    sample_rate_hz = getattr(device, "sample_rate_hz", 4.0)
    manifest = SessionManifest(
        path=manifest_path,
        session_id=session_id,
        label_mode=label_mode,
        dry_run=dry_run,
        sample_rate_hz=sample_rate_hz,
    )

    writer = TrialCSVWriter(csv_path)
    try:
        _show(f"\n=== Session {session_num} - BASELINE (sit still, eyes open) ===")
        _countdown(BASELINE_S)
        baseline = []
        manifest.set_baseline(_summarize_baseline(baseline))

        rng = random.Random(session_num * 97 + 13)
        labels = (["CONFIRM"] * (TRIALS_PER_SESSION // 2) +
                  ["IDLE"] * (TRIALS_PER_SESSION - TRIALS_PER_SESSION // 2))
        rng.shuffle(labels)

        for trial_num, label in enumerate(labels, start=1):
            trial_id = f"{session_id}_trial_{trial_num:03d}"
            _show(f"\nTrial {trial_num:2d}/{TRIALS_PER_SESSION}", end="  ")

            _show_cue(".  .  .  REST", TRIAL_PROTOCOL["rest_s"])
            _show_cue(_cue_text(label, label_mode), TRIAL_PROTOCOL["cue_s"])

            sample_buffer.clear()
            start_ms = time.time() * 1000.0

            if dry_run:
                dry_device = _DryRunDevice()
                dry_device._rng.seed(trial_num * 7)
                n_samples = int(TRIAL_PROTOCOL["action_s"] * sample_rate_hz)
                for k in range(n_samples):
                    sample = _DryRunSample(
                        dry_device._rng,
                        t_ms=start_ms + k * (1000.0 / sample_rate_hz),
                    )
                    _attach_device_stats(sample, device.get_device_stats())
                    sample_buffer.append(sample)
                time.sleep(TRIAL_PROTOCOL["action_s"])
            else:
                if callback_mode:
                    _show_cue("[  WINDOW  ]", TRIAL_PROTOCOL["action_s"])
                else:
                    sample_buffer[:] = _collect_window(
                        device,
                        sample_buffer,
                        dry_run,
                        label,
                        TRIAL_PROTOCOL["action_s"],
                        callback_mode,
                    )

            end_ms = time.time() * 1000.0
            collected = list(sample_buffer)

            _show_cue(".  .  .", TRIAL_PROTOCOL["post_rest_s"])

            writer.write_trial(collected, label, trial_id)

            values = [sample.value for sample in collected] or [0.0]
            valid_count = sum(1 for sample in collected if sample.valid)

            dev_stats = _get_device_stats(device)
            sig_q = dev_stats.get("signal_quality", None)
            attention = dev_stats.get("attention", None)
            meditation = dev_stats.get("meditation", None)

            warning = None
            if len(collected) < MIN_SAMPLES_PER_TRIAL:
                warning = f"LOW_SAMPLES:{len(collected)}"
                print(f"  WARNING Only {len(collected)} sample(s) - check BrainLink connection")
            elif valid_count / max(len(collected), 1) < QUALITY_WARN_THRESHOLD:
                warning = f"LOW_VALID_RATE:{valid_count}/{len(collected)}"
                print(f"  WARNING Low valid rate: {valid_count}/{len(collected)} samples valid")

            if sig_q is not None and sig_q > 100:
                note = f"POOR_SIGNAL:{sig_q}"
                warning = f"{warning},{note}" if warning else note
                print(f"  WARNING Poor BrainLink signal quality: {sig_q} (target < 50)")

            trial_rec = TrialRecord(
                trial_id=trial_id,
                label=label,
                sample_count=len(collected),
                mean_value=sum(values) / len(values),
                min_value=min(values),
                max_value=max(values),
                valid_sample_rate=valid_count / max(len(collected), 1),
                timing_start_ms=start_ms,
                timing_end_ms=end_ms,
                duration_actual_s=(end_ms - start_ms) / 1000.0,
                device_signal_quality=sig_q,
                device_attention=attention,
                device_meditation=meditation,
                warning=warning,
            )
            manifest.record_trial(trial_rec)

            q_str = f"  sig={sig_q}" if sig_q is not None else ""
            a_str = f" att={attention}" if attention is not None else ""
            print(
                f"  {label:8s}  n={len(collected):2d}{q_str}{a_str}  "
                f"{'WARNING ' + warning if warning else 'OK'}"
            )
    finally:
        writer.close()
        manifest.close()

    print(f"\n  CSV:      {csv_path}")
    print(f"  Manifest: {manifest_path}")
    _print_session_summary(manifest_path)

    return csv_path


def _balanced_labels(session_num: int, session_id: str) -> list[str]:
    stable_session_hash = int(sha256(session_id.encode("utf-8")).hexdigest()[:8], 16)
    seed = session_num * 42 + (stable_session_hash % 10_000)
    rng = random.Random(seed)
    n_confirm = TRIALS_PER_SESSION // 2
    labels = ["CONFIRM"] * n_confirm
    labels.extend(["IDLE"] * (TRIALS_PER_SESSION - n_confirm))
    rng.shuffle(labels)
    return labels


def _collect_window(
    device,
    sample_buffer: list,
    dry_run: bool,
    label: str,
    duration_s: float,
    callback_mode: bool,
) -> list[object]:
    print(f"\r[ WINDOW ]{'':<21}", end="", flush=True)
    start_s = time.time()

    if callback_mode:
        sample_buffer.clear()
        time.sleep(duration_s)
        return list(sample_buffer)

    samples = []
    sample_interval_s = 1.0 / max(1.0, _device_sample_rate(device, dry_run))
    next_sample_s = start_s
    while time.time() - start_s < duration_s:
        now = time.time()
        if dry_run:
            if now >= next_sample_s:
                sample = device.read_sample()
                _attach_device_stats(sample, _get_device_stats(device))
                samples.append(sample)
                next_sample_s += sample_interval_s
            time.sleep(min(POLL_INTERVAL_S, sample_interval_s / 4.0))
        else:
            sample = device.read_sample()
            if sample is not None:
                samples.append(sample)
            time.sleep(POLL_INTERVAL_S)
    return samples


def _summarize_trial(
    session_id: str,
    trial_index: int,
    label: str,
    samples: list[object],
    started_at_ms: float,
    ended_at_ms: float,
    device_stats: Optional[dict] = None,
) -> TrialRecord:
    qualities = [float(getattr(sample, "quality", 1.0)) for sample in samples]
    valids = [1.0 if bool(getattr(sample, "valid", True)) else 0.0 for sample in samples]
    values = [float(getattr(sample, "value", 0.0)) for sample in samples]
    warning = None
    mean_quality = _mean_or_zero(qualities)
    if len(samples) < MIN_SAMPLES_PER_TRIAL:
        warning = f"low sample count ({len(samples)})"
    elif mean_quality < QUALITY_WARN_THRESHOLD:
        warning = f"low mean quality ({mean_quality:.3f})"

    return TrialRecord(
        trial_id=f"{session_id}_trial_{trial_index:03d}",
        label=label,
        sample_count=len(samples),
        mean_value=_mean_or_zero(values),
        min_value=min(values) if values else 0.0,
        max_value=max(values) if values else 0.0,
        valid_sample_rate=_mean_or_zero(valids),
        timing_start_ms=started_at_ms,
        timing_end_ms=ended_at_ms,
        duration_actual_s=(ended_at_ms - started_at_ms) / 1000.0,
        device_signal_quality=_stat_int(device_stats, "signal_quality", _last_int_optional(_metadata_values(samples, "poor_signal"))),
        device_attention=_stat_int(device_stats, "attention", _last_int_optional(_metadata_values(samples, "attention"))),
        device_meditation=_stat_int(device_stats, "meditation", _last_int_optional(_metadata_values(samples, "meditation"))),
        warning=warning,
    )


def _trial_index_from_id(trial_id: str) -> int:
    try:
        return int(trial_id.rsplit("_", 1)[-1])
    except ValueError:
        return int(trial_id)


def _summarize_baseline(samples: list[object]) -> dict:
    qualities = [float(getattr(sample, "quality", 1.0)) for sample in samples]
    return {
        "sample_count": len(samples),
        "mean_quality": _mean_or_zero(qualities),
        "signal_quality_mean": _mean_optional(_metadata_values(samples, "poor_signal"), invert_poor_signal=True),
        "attention_mean": _mean_optional(_metadata_values(samples, "attention")),
        "meditation_mean": _mean_optional(_metadata_values(samples, "meditation")),
    }


def _metadata_values(samples: list[object], key: str) -> list[float]:
    values = []
    for sample in samples:
        metadata = getattr(sample, "metadata", {}) or {}
        value = metadata.get(key)
        if value is not None:
            values.append(float(value))
    return values


def _get_device_stats(device) -> dict:
    if device is None or not hasattr(device, "get_device_stats"):
        return {}
    try:
        return dict(device.get_device_stats() or {})
    except Exception:
        return {}


def _attach_device_stats(sample: object, stats: dict) -> None:
    metadata = dict(getattr(sample, "metadata", {}) or {})
    if "signal_quality" in stats:
        metadata["signal_quality"] = stats["signal_quality"]
        metadata["poor_signal"] = stats["signal_quality"]
    if "attention" in stats:
        metadata["attention"] = stats["attention"]
    if "meditation" in stats:
        metadata["meditation"] = stats["meditation"]
    sample.metadata = metadata


def _mean_or_zero(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _mean_optional(values: list[float], invert_poor_signal: bool = False) -> Optional[float]:
    if not values:
        return None
    if invert_poor_signal:
        converted = [max(0.0, min(1.0, 1.0 - (value / 200.0))) for value in values]
        return float(sum(converted) / len(converted))
    return float(sum(values) / len(values))


def _max_optional(values: list[float]) -> Optional[float]:
    return max(values) if values else None


def _last_int_optional(values: list[float]) -> Optional[int]:
    return int(values[-1]) if values else None


def _stat_int(stats: Optional[dict], key: str, fallback: Optional[int]) -> Optional[int]:
    if stats and stats.get(key) is not None:
        return int(stats[key])
    return fallback


def _get_cue_text(label: str, mode: str) -> str:
    if label == "CONFIRM":
        return {"blink": "*** BLINK NOW ***", "focus": "*** FOCUS ***"}.get(mode, "*** CONFIRM ***")
    return "     (do nothing)     "


def _cue_text(label: str, mode: str) -> str:
    return _get_cue_text(label, mode)


def _show(text: str, end: str = "\n") -> None:
    print(text, end=end, flush=True)


def _countdown(duration_s: float) -> None:
    end = time.monotonic() + duration_s
    while True:
        remaining = end - time.monotonic()
        if remaining <= 0:
            break
        print(f"\r  Baseline: {int(remaining):3d}s remaining  ", end="", flush=True)
        time.sleep(min(1.0, remaining))
    print()


def _show_cue(text: str, duration_s: float) -> None:
    print(f"\r  {text:<30}", end="", flush=True)
    time.sleep(duration_s)


def _print_session_summary(manifest_path: Path) -> None:
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    trials = data.get("trials", [])
    if not trials:
        return
    confirms = [trial for trial in trials if trial["label"] == "CONFIRM"]
    idles = [trial for trial in trials if trial["label"] == "IDLE"]
    warned = [trial for trial in trials if trial.get("warning")]
    total_samples = sum(trial["sample_count"] for trial in trials)
    mean_valid = sum(trial["valid_sample_rate"] for trial in trials) / max(len(trials), 1)
    print(f"\n  Trials:   {len(trials)} ({len(confirms)} CONFIRM, {len(idles)} IDLE)")
    print(
        f"  Samples:  {total_samples} total  "
        f"({total_samples / max(len(trials), 1):.1f} per trial)"
    )
    print(f"  Quality:  {mean_valid:.2%} valid sample rate")
    if warned:
        print(f"  WARNING {len(warned)} trial(s) had quality warnings")
    sig_qs = [
        trial["device_signal_quality"]
        for trial in trials
        if trial.get("device_signal_quality") is not None
    ]
    if sig_qs:
        print(f"  Signal:   mean={sum(sig_qs) / len(sig_qs):.0f}  (0=good, 200=poor)")


def _flush_file(f) -> None:
    f.flush()
    os.fsync(f.fileno())


def _read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _manifest_path_for(csv_path: Path) -> Path:
    new_path = csv_path.with_suffix(".manifest.json")
    if new_path.exists():
        return new_path
    old_path = csv_path.with_name(f"{csv_path.stem}_manifest.json")
    return old_path if old_path.exists() else new_path


def _latest_session_csv(raw_dir: Path) -> Optional[Path]:
    sessions = sorted(raw_dir.glob("session_*.csv"), key=lambda path: path.stat().st_mtime)
    return sessions[-1] if sessions else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=4)
    parser.add_argument("--label-mode", choices=["blink", "focus"], default="blink")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", default="data/eeg_training/raw")
    args = parser.parse_args()
    return run_collection(
        sessions=args.sessions,
        dry_run=args.dry_run,
        label_mode=args.label_mode,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
