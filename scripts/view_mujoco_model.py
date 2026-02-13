#!/usr/bin/env python3
"""View a MuJoCo model interactively or render one headless frame."""

import argparse
import os
import sys
from pathlib import Path

import mujoco


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="View MuJoCo model")
    parser.add_argument(
        "--model",
        default=os.path.join("models", "kuka_iiwa", "model.xml"),
        help="Path to MuJoCo XML model",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Render one offscreen frame instead of launching interactive viewer",
    )
    parser.add_argument(
        "--out",
        default=os.path.join("data", "logs", "mujoco_preview.png"),
        help="Output image path for headless mode",
    )
    parser.add_argument("--width", type=int, default=640, help="Headless render width")
    parser.add_argument("--height", type=int, default=480, help="Headless render height")
    return parser.parse_args()


def save_image(path: str, pixels) -> None:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image

        Image.fromarray(pixels).save(out_path)
        print(f"Saved preview to {out_path}")
        return
    except Exception:
        pass

    try:
        import matplotlib.pyplot as plt

        plt.imsave(out_path, pixels)
        print(f"Saved preview to {out_path}")
        return
    except Exception as exc:
        raise RuntimeError(
            "Could not save image; install Pillow or matplotlib."
        ) from exc


def main() -> None:
    args = parse_args()
    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    model = mujoco.MjModel.from_xml_path(str(model_path))
    data = mujoco.MjData(model)

    if args.headless:
        try:
            renderer = mujoco.Renderer(model, height=args.height, width=args.width)
            mujoco.mj_forward(model, data)
            renderer.update_scene(data)
            pixels = renderer.render()
            save_image(args.out, pixels)
        except Exception as exc:
            print(
                "Headless render failed. This session likely has no usable GL context.\n"
                "Try one of:\n"
                "  1) Run from a desktop terminal (GUI login session).\n"
                "  2) Use interactive viewer mode without --headless.\n"
                "  3) On CI/Linux, install/configure OSMesa/EGL and set MUJOCO_GL accordingly.\n"
                f"Original error: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(2)
        return

    try:
        import mujoco.viewer as mj_viewer

        mj_viewer.launch(model, data)
    except Exception as exc:
        print(
            "Interactive viewer failed. Ensure you are in a GUI desktop session.\n"
            f"Original error: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
