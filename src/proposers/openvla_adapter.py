"""
OpenVLA Adapter - supports both real model and fake fallback.

Backend is controlled by config:
  openvla.backend: "real" | "fake"

The fake adapter is always available and should remain the default in
configs/default.yaml so simulation continues to work without GPU access.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class OpenVLAAdapter:
    """
    Unified adapter: routes to real or fake backend based on config.

    predict(instruction, image) -> np.ndarray shape (7,)
    [dx, dy, dz, droll, dpitch, dyaw, gripper_open]
    """

    def __init__(
        self,
        backend: str = "fake",
        device: str = "mps",
        dtype: str = "float16",
        model_name: str = "openvla/openvla-7b",
    ):
        self._backend = backend
        self._model = None
        self._processor = None
        self._device = device
        self._dtype = dtype
        self._model_name = model_name

        if backend == "real":
            self._load_real_model()

    def predict(self, instruction: str, image: np.ndarray) -> np.ndarray:
        """
        Args:
            instruction: natural language task description
            image: (H, W, 3) uint8 RGB frame
        Returns:
            delta_action: np.ndarray shape (7,), dtype float32
        """
        if self._backend == "real" and self._model is not None:
            return self._predict_real(instruction, image)
        return self._predict_fake(instruction, image)

    def _load_real_model(self) -> None:
        try:
            import torch
            from transformers import AutoModelForVision2Seq, AutoProcessor

            dtype = torch.float16 if self._dtype == "float16" else torch.float32
            self._processor = AutoProcessor.from_pretrained(
                self._model_name,
                trust_remote_code=True,
            )
            self._model = AutoModelForVision2Seq.from_pretrained(
                self._model_name,
                torch_dtype=dtype,
                trust_remote_code=True,
            ).to(self._device)
            self._model.eval()
        except Exception as exc:
            logger.warning(
                "OpenVLA real model failed to load (%s). Falling back to fake.",
                exc,
            )
            self._model = None

    def _predict_real(self, instruction: str, image: np.ndarray) -> np.ndarray:
        import torch
        from PIL import Image

        pil_image = Image.fromarray(image)
        prompt = f"In: What action should the robot take to {instruction}?\nOut:"
        inputs = self._processor(prompt, pil_image, return_tensors="pt")
        inputs = {key: value.to(self._device) for key, value in inputs.items()}
        with torch.no_grad():
            action = self._model.predict_action(**inputs)
        if hasattr(action, "detach"):
            action = action.detach().cpu().numpy()
        return np.asarray(action, dtype=np.float32).reshape(7)

    @staticmethod
    def _predict_fake(instruction: str, image: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Returns a plausible small deterministic delta action.
        Used in simulation when real model is not available.
        """
        seed = abs(hash((instruction, getattr(image, "shape", None)))) % (2**31)
        rng = np.random.default_rng(seed=seed)
        delta = rng.normal(0, 0.02, size=7).astype(np.float32)
        delta[6] = float(rng.random() > 0.5)
        return delta

    @property
    def is_loaded(self) -> bool:
        return self._backend == "fake" or self._model is not None
