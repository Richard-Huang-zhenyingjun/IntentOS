"""
Fake OpenVLA adapter for testing and CI.

Returns deterministic actions without loading the real model.
Use this in tests and headless CI where GPU/model weights aren't available.
"""
from __future__ import annotations

import numpy as np

from src.external.openvla.adapter import OpenVLAAction


class FakeOpenVLAAdapter:
    """
    Drop-in replacement for OpenVLAAdapter that returns deterministic actions.

    Action semantics:
    - "pick" instructions → move down + close gripper
    - "place" instructions → move to target + open gripper
    - Unknown → small random movement
    """

    def __init__(self):
        self._is_loaded = False
        self._call_count = 0

    def load_model(self) -> None:
        self._is_loaded = True

    def predict(self, instruction: str, image: np.ndarray) -> OpenVLAAction:
        assert self._is_loaded, "Call load_model() first"
        self._call_count += 1

        instruction_lower = instruction.lower()

        if "pick" in instruction_lower or "grab" in instruction_lower:
            # Move down and close gripper
            action = np.array([0.0, 0.0, -0.02, 0.0, 0.0, 0.0, 0.0])
        elif "place" in instruction_lower or "put" in instruction_lower:
            # Move to side and open gripper
            action = np.array([0.02, 0.0, 0.01, 0.0, 0.0, 0.0, 1.0])
        elif "move" in instruction_lower:
            # Move forward
            action = np.array([0.02, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5])
        else:
            # Small default movement
            action = np.array([0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5])

        return OpenVLAAction(
            delta_position=action[:3],
            delta_rotation=action[3:6],
            gripper=float(action[6]),
            raw_action=action,
            instruction=instruction,
            confidence=0.95,
        )

    def predict_batch(
        self, instruction: str, images: list[np.ndarray]
    ) -> list[OpenVLAAction]:
        return [self.predict(instruction, img) for img in images]

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    @property
    def action_dim(self) -> int:
        return 7

    @property
    def call_count(self) -> int:
        return self._call_count

    def close(self) -> None:
        self._is_loaded = False
