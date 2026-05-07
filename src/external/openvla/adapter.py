"""
OpenVLA Adapter — supports both real model and fake fallback.

Backend is controlled by config:
  openvla.backend: "real" | "fake"

The fake adapter is always available and remains the default in configs/default.yaml
so simulation continues to work without GPU access.

Usage:
    adapter = OpenVLAAdapter(backend="fake")
    adapter.load_model()
    action = adapter.predict("pick up the red cup", image)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np
import yaml

logger = logging.getLogger(__name__)


@dataclass
class OpenVLAAction:
    """Structured output from OpenVLA inference."""
    delta_position: np.ndarray      # [dx, dy, dz] in meters
    delta_rotation: np.ndarray      # [droll, dpitch, dyaw] in radians
    gripper: float                  # 0.0 = close, 1.0 = open
    raw_action: np.ndarray          # Full 7-dim raw output
    instruction: str                # The input instruction
    confidence: float = 1.0         # Placeholder for future confidence estimation


class OpenVLAAdapter:
    """
    Unified adapter for OpenVLA real and fake backends.

    predict(instruction, image) -> OpenVLAAction with raw_action shape (7,)
    [dx, dy, dz, droll, dpitch, dyaw, gripper_open]
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        backend: str = "real",
        device: Optional[str] = None,
        dtype: Optional[str] = None,
    ):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__), "config.yaml"
            )

        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)

        self._model = None
        self._processor = None
        self._is_loaded = False
        self._device = None
        self._backend = backend
        self._device_override = device
        self._dtype_override = dtype

    def load_model(self) -> None:
        """
        Load selected backend.

        First call downloads weights (~15GB for 7B model).
        Subsequent calls use cached weights.
        """
        if self._backend == "fake":
            self._is_loaded = True
            self._device = "fake"
            logger.info("OpenVLA fake backend ready")
            return

        try:
            from transformers import AutoModelForVision2Seq, AutoProcessor
            import torch
        except ImportError as e:
            raise ImportError(
                "OpenVLA requires: pip install transformers torch torchvision"
            ) from e

        model_name = self._config["model"]["name"]
        device_str = self._device_override or self._config["model"]["device"]
        dtype_str = self._dtype_override or self._config["model"]["torch_dtype"]

        # Resolve device
        if device_str == "auto":
            if torch.cuda.is_available():
                self._device = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                self._device = "mps"
            else:
                self._device = "cpu"
        else:
            self._device = device_str

        # Resolve dtype
        dtype_map = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }
        torch_dtype = dtype_map.get(dtype_str, torch.float32)
        if self._device == "cpu" and torch_dtype != torch.float32:
            logger.warning("CPU mode: forcing float32 (bfloat16/float16 slow on CPU)")
            torch_dtype = torch.float32

        logger.info(f"Loading OpenVLA model: {model_name} on {self._device} ({torch_dtype})")

        self._processor = AutoProcessor.from_pretrained(
            model_name, trust_remote_code=True
        )
        self._model = AutoModelForVision2Seq.from_pretrained(
            model_name,
            torch_dtype=torch_dtype,
            trust_remote_code=True,
        )
        self._model = self._model.to(self._device)
        self._model.eval()

        self._is_loaded = True
        logger.info(f"OpenVLA model loaded successfully on {self._device}")

    def predict(self, instruction: str, image: np.ndarray) -> OpenVLAAction:
        """
        Run OpenVLA inference.

        Args:
            instruction: Natural language task description.
                         Example: "pick up the red cube"
            image: RGB image as np.ndarray, shape (H, W, 3), dtype uint8.
                   Will be resized to 224x224 internally.

        Returns:
            OpenVLAAction with delta EE commands and gripper state.
        """
        assert self._is_loaded, "Call load_model() first"

        if self._backend == "fake" or self._model is None:
            raw = self._predict_fake_array(instruction, image)
            return self._wrap_action(raw, instruction, confidence=0.95)

        from PIL import Image
        import torch

        # Convert numpy to PIL
        if image.dtype != np.uint8:
            image = (image * 255).astype(np.uint8)
        pil_image = Image.fromarray(image).resize(
            tuple(self._config["inference"]["image_size"])
        )

        # Format prompt (OpenVLA expects specific format)
        prompt = f"In: What action should the robot take to {instruction}?\nOut:"

        # Tokenize
        inputs = self._processor(prompt, pil_image, return_tensors="pt")
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        # Inference
        with torch.no_grad():
            action = self._model.predict_action(**inputs)

        # action should be a numpy array of shape (7,)
        if isinstance(action, torch.Tensor):
            action = action.cpu().numpy()

        raw = np.array(action, dtype=np.float64).flatten()

        # Safety clamp
        raw = self._clamp_action(raw)
        return self._wrap_action(raw, instruction)

    def _wrap_action(
        self,
        raw: np.ndarray,
        instruction: str,
        confidence: float = 1.0,
    ) -> OpenVLAAction:
        raw = np.asarray(raw, dtype=np.float64).flatten()
        if raw.shape[0] < 7:
            raw = np.pad(raw, (0, 7 - raw.shape[0]), constant_values=0.0)
        raw = raw[:7]
        return OpenVLAAction(
            delta_position=raw[:3],
            delta_rotation=raw[3:6],
            gripper=float(raw[6]) if len(raw) > 6 else 1.0,
            raw_action=raw,
            instruction=instruction,
            confidence=confidence,
        )

    def predict_batch(
        self, instruction: str, images: list[np.ndarray]
    ) -> list[OpenVLAAction]:
        """Run inference on multiple images (for trajectory generation)."""
        return [self.predict(instruction, img) for img in images]

    def _clamp_action(self, action: np.ndarray) -> np.ndarray:
        """Clamp actions to safe bounds defined in config."""
        cfg = self._config["action_space"]
        pos_max = cfg["position_delta_max"]
        rot_max = cfg["rotation_delta_max"]

        clamped = action.copy()
        clamped[:3] = np.clip(clamped[:3], -pos_max, pos_max)
        clamped[3:6] = np.clip(clamped[3:6], -rot_max, rot_max)
        if len(clamped) > 6:
            clamped[6] = np.clip(clamped[6], 0.0, 1.0)
        return clamped

    @staticmethod
    def _predict_fake_array(instruction: str, image: np.ndarray) -> np.ndarray:
        """
        Returns a plausible small deterministic delta action.
        Used in simulation when the real model is not available.
        """
        seed = abs(hash((instruction, getattr(image, "shape", None)))) % (2**31)
        rng = np.random.default_rng(seed=seed)
        delta = rng.normal(0, 0.02, size=7).astype(np.float32)
        delta[6] = float(rng.random() > 0.5)
        return delta

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @property
    def action_dim(self) -> int:
        return self._config["action_space"]["dimensions"]

    def close(self) -> None:
        """Release model from GPU memory."""
        if self._model is not None:
            del self._model
            self._model = None
        if self._processor is not None:
            del self._processor
            self._processor = None
        self._is_loaded = False

        # Clear CUDA cache
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

        logger.info("OpenVLA adapter closed")
