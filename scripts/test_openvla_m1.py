#!/usr/bin/env python3
"""
OpenVLA M1 Pro compatibility test.

Tests the real 7B model on MPS backend and benchmarks inference time.
Determines whether real model is viable for demo.

Requirements:
    pip install transformers accelerate pillow torch

Usage:
    python scripts/test_openvla_m1.py
    python scripts/test_openvla_m1.py --quantize int8   # if float16 OOM

Exit codes:
    0 = viable or slow-but-usable model load/inference succeeded
    1 = not viable (OOM or inference error) - use fake adapter
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

import numpy as np


MODEL_NAME = "openvla/openvla-7b"
RESULTS_PATH = Path("docs/openvla_m1_results.txt")


def test_openvla(quantize: str | None) -> int:
    print("=== OpenVLA M1 Pro Viability Test ===\n")
    results = {
        "model": MODEL_NAME,
        "requested_quantize": quantize or "none",
        "device": "unknown",
        "dtype": "unknown",
        "load_time_s": None,
        "mean_inference_s": None,
        "action_shape": None,
        "action_range": None,
        "verdict": "not viable",
        "recommended_config": 'openvla.backend: "fake"',
        "error": "",
    }

    if not _check_backends(results):
        print("\nBackend check failed. Use fake adapter.")
        _write_results(results)
        return 1
    _check_memory(results)

    model, processor, device = _load_model(quantize, results)
    if model is None:
        print("\nModel failed to load. Use fake adapter.")
        _write_results(results)
        return 1

    success, avg_time = _benchmark_inference(model, processor, device, results)

    print(f"\n{'=' * 40}")
    if success and avg_time < 2.0:
        print(f"VIABLE - mean inference: {avg_time:.2f}s")
        print("Update OpenVLA config to use the real adapter.")
        print(f"  device: {device}, quantize: {quantize or 'float16'}")
        results["verdict"] = "viable"
        results["recommended_config"] = (
            'openvla:\n'
            '  backend: "real"\n'
            f'  device: "{device}"\n'
            '  dtype: "float16"'
        )
        _write_results(results)
        return 0
    if success:
        print(f"SLOW - mean inference: {avg_time:.2f}s (> 2s target)")
        print("May be usable with a progress indicator. Check demo requirements.")
        results["verdict"] = "not viable for <2s target (slow)"
        results["recommended_config"] = (
            'openvla:\n'
            '  backend: "fake"  # real model loaded but exceeded 2s target'
        )
        _write_results(results)
        return 0

    print("NOT VIABLE - OOM or inference error. Use fake adapter.")
    _write_results(results)
    return 1


def _check_backends(results: dict) -> bool:
    try:
        import torch
    except Exception as exc:
        print(f"PyTorch unavailable: {exc}")
        results["error"] = f"PyTorch unavailable: {exc}"
        return False

    print(f"PyTorch version: {torch.__version__}")
    print(f"MPS available:   {torch.backends.mps.is_available()}")
    print(f"MPS built:       {torch.backends.mps.is_built()}")
    print()
    results["torch_version"] = torch.__version__
    results["mps_available"] = str(torch.backends.mps.is_available())
    results["mps_built"] = str(torch.backends.mps.is_built())
    return True


def _check_memory(results: dict) -> None:
    try:
        import psutil

        mem = psutil.virtual_memory()
        print(f"Total RAM: {mem.total / 1e9:.1f} GB")
        print(f"Available: {mem.available / 1e9:.1f} GB")
        results["total_ram_gb"] = f"{mem.total / 1e9:.1f}"
        results["available_ram_gb"] = f"{mem.available / 1e9:.1f}"
        if mem.available < 14e9:
            print("WARNING: < 14GB available - float16 load may OOM. Try --quantize int8")
    except ImportError:
        print("(psutil not installed - skip memory check)")
        results["memory_check"] = "psutil not installed"
    print()


def _load_model(quantize: str | None, results: dict):
    try:
        import torch
        from transformers import AutoModelForVision2Seq, AutoProcessor

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.float16 if device == "mps" else torch.float32
        results["device"] = device
        results["dtype"] = str(dtype).replace("torch.", "")

        print(f"Loading {MODEL_NAME} on {device} ({dtype})...")
        t0 = time.time()

        load_kwargs = {"torch_dtype": dtype, "trust_remote_code": True}
        if quantize == "int8":
            load_kwargs["load_in_8bit"] = True

        processor = AutoProcessor.from_pretrained(MODEL_NAME, trust_remote_code=True)
        model = AutoModelForVision2Seq.from_pretrained(MODEL_NAME, **load_kwargs)
        if quantize != "int8":
            model = model.to(device)
        model.eval()

        load_time = time.time() - t0
        results["load_time_s"] = f"{load_time:.3f}"
        print(f"Model loaded in {load_time:.1f}s")
        return model, processor, device
    except Exception as exc:
        if "t0" in locals():
            results["load_time_s"] = f"{time.time() - t0:.3f}"
        print(f"Load failed: {exc}")
        results["error"] = f"Load failed: {exc}"
        if "out of memory" in str(exc).lower():
            print("Try: python scripts/test_openvla_m1.py --quantize int8")
        return None, None, None


def _benchmark_inference(model, processor, device: str, results: dict, n_trials: int = 3):
    """Run N inference passes, report mean and action output format."""
    import torch
    from PIL import Image

    times = []
    last_action = None

    print(f"\nRunning {n_trials} inference trials...")
    dummy_image = Image.fromarray(
        np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    )
    instruction = "pick up the red block"
    prompt = f"In: What action should the robot take to {instruction}?\nOut:"

    for i in range(n_trials):
        try:
            inputs = processor(prompt, dummy_image, return_tensors="pt")
            inputs = {key: value.to(device) for key, value in inputs.items()}

            t0 = time.time()
            with torch.no_grad():
                outputs = model.predict_action(**inputs)
            elapsed = time.time() - t0

            action = outputs.detach().cpu().numpy() if hasattr(outputs, "detach") else np.asarray(outputs)
            action = np.asarray(action, dtype=np.float64).flatten()
            times.append(elapsed)
            last_action = action

            print(f"  Trial {i + 1}: {elapsed:.3f}s  action={np.round(action, 3)}")
        except Exception as exc:
            print(f"  Trial {i + 1}: FAILED - {exc}")
            traceback.print_exc()
            results["error"] = f"Inference failed: {exc}"
            return False, 999.0

    avg = sum(times) / len(times)
    results["mean_inference_s"] = f"{avg:.3f}"
    results["action_shape"] = str(tuple(np.array(last_action).shape))
    results["action_range"] = f"[{np.min(last_action):.3f}, {np.max(last_action):.3f}]"
    print(f"\nMean: {avg:.3f}s  |  Action shape: {np.array(last_action).shape}")
    print(f"Action range: [{np.min(last_action):.3f}, {np.max(last_action):.3f}]")
    print("Action format: [dx, dy, dz, droll, dpitch, dyaw, gripper_open]")
    return True, avg


def _write_results(results: dict) -> None:
    def value(name: str, fallback: str) -> str:
        item = results.get(name)
        return fallback if item is None else str(item)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# OpenVLA M1 Results",
        "",
        f"Model: {value('model', MODEL_NAME)}",
        f"Device: {value('device', 'unknown')}",
        f"Dtype/precision: {value('dtype', 'unknown')}",
        f"Quantize: {value('requested_quantize', 'none')}",
        f"PyTorch: {value('torch_version', 'unavailable')}",
        f"MPS available: {value('mps_available', 'unknown')}",
        f"MPS built: {value('mps_built', 'unknown')}",
        f"Total RAM GB: {value('total_ram_gb', 'unknown')}",
        f"Available RAM GB: {value('available_ram_gb', 'unknown')}",
        f"Load time s: {value('load_time_s', 'not loaded')}",
        f"Mean inference s: {value('mean_inference_s', 'not run')}",
        f"Action shape: {value('action_shape', 'not run')}",
        f"Action value range: {value('action_range', 'not run')}",
        f"Verdict: {value('verdict', 'not viable')}",
        "",
        "Fallback chain:",
        "1. Try `openvla.backend: \"real\"` only if this test reports viable.",
        "2. If model load fails, inference fails, or mean inference exceeds the demo target, keep `openvla.backend: \"fake\"`.",
        "3. `configs/default.yaml` keeps fake as the default so simulation and smoke tests do not require model weights.",
        "",
        "Recommended config:",
        "```yaml",
        str(results.get("recommended_config", 'openvla.backend: "fake"')),
        "```",
    ]
    if results.get("error"):
        lines.extend(["", f"Error: {results['error']}"])
    RESULTS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nResults written -> {RESULTS_PATH}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quantize", choices=["int8"], default=None)
    args = parser.parse_args()
    return test_openvla(args.quantize)


if __name__ == "__main__":
    raise SystemExit(main())
