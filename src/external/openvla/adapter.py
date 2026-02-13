"""
OpenVLA Model Adapter.

Wraps the OpenVLA model for use in the Intent-Authorized system.
This is a STANDALONE wrapper — no dependencies on the intent system.
Integration with ProposerRegistry happens in Week 2.

Usage:
    adapter = OpenVLAAdapter()
    adapter.load_model()
    action = adapter.predict("pick up the red cup", image)
    # action = np.array([dx, dy, dz, droll, dpitch, dyaw, gripper])
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
    Adapter for OpenVLA vision-language-action model.

    Handles model loading, image preprocessing, inference, and
    action postprocessing. Designed to be used standalone for testing
    (Week 1) and later wrapped by OpenVLAProposer (Week 2).
    """

    def __init__(self, config_path: Optional[str] = None):
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

    def load_model(self) -> None:
        """
        Load OpenVLA model from HuggingFace.

        First call downloads weights (~15GB for 7B model).
        Subsequent calls use cached weights.
        """
        try:
            from transformers import AutoModelForVision2Seq, AutoProcessor
            import torch
        except ImportError as e:
            raise ImportError(
                "OpenVLA requires: pip install transformers torch torchvision"
            ) from e

        model_name = self._config["model"]["name"]
        device_str = self._config["model"]["device"]
        dtype_str = self._config["model"]["torch_dtype"]

        # Resolve device
        if device_str == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
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
        ).to(self._device)

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

        return OpenVLAAction(
            delta_position=raw[:3],
            delta_rotation=raw[3:6],
            gripper=float(raw[6]) if len(raw) > 6 else 1.0,
            raw_action=raw,
            instruction=instruction,
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
