"""
OpenVLA Proposer — integrates OpenVLA into the ProposerRegistry.

This is a Tier 2A component that proposes actions only.
It never executes robot motion.
"""
from __future__ import annotations

import logging
from typing import Optional, Protocol

import numpy as np

from src.external.openvla.adapter import OpenVLAAction
from src.interfaces.intent_proposal import ActionType, IntentProposal
from src.interfaces.primitive import PrimitiveType
from src.interfaces.proposer_base import ProposerBase
from src.interfaces.scene_summary import ObjectInfo, SceneSummary

logger = logging.getLogger(__name__)


class CameraProvider(Protocol):
    """Protocol for simulation backends that can render RGB frames."""

    def render_camera(self, camera_name: str = "") -> np.ndarray: ...


class OpenVLAProposer(ProposerBase):
    """
    Proposer that uses OpenVLA (real or fake adapter) to generate proposals.

    Returns IntentProposal only; execution remains gated by orchestrator auth flow.
    """

    def __init__(
        self,
        openvla_adapter,
        camera_provider: Optional[CameraProvider] = None,
        camera_name: str = "overhead",
        priority: int = 15,
        enabled: bool = True,
    ):
        self._adapter = openvla_adapter
        self._camera = camera_provider
        self._camera_name = camera_name
        self._priority = priority
        self._enabled = enabled
        self._last_action: Optional[OpenVLAAction] = None
        self._proposal_count = 0
        self._failure_count = 0

    def name(self) -> str:
        return "openvla"

    @property
    def priority(self) -> int:
        return self._priority

    def is_available(self) -> bool:
        return self._enabled and bool(getattr(self._adapter, "is_loaded", False))

    def propose(self, scene: SceneSummary) -> IntentProposal:
        """
        Generate proposal from scene with OpenVLA.

        On failure, returns IDLE with confidence=0.0 so registry can fall back.
        """
        if not self.is_available():
            return self._fallback_signal("adapter_unavailable")

        target_object = self._select_target_object(scene)
        if target_object is None:
            return self._fallback_signal("no_target_object")

        try:
            instruction = self._build_instruction(target_object, scene)
            image = self._get_camera_image(scene)
            action = self._adapter.predict(instruction, image)

            self._last_action = action
            self._proposal_count += 1

            proposal = self._build_proposal(action, target_object, scene)
            logger.info(
                "[OPENVLA] proposal #%d instruction='%s' delta=%s",
                self._proposal_count,
                instruction,
                action.delta_position,
            )
            return proposal
        except Exception as exc:
            self._failure_count += 1
            logger.warning("[OPENVLA] propose failed: %s", exc)
            return self._fallback_signal(f"openvla_error:{exc}")

    def _select_target_object(self, scene: SceneSummary) -> Optional[ObjectInfo]:
        """Deterministic target pick from on-table objects only."""
        candidates = scene.objects_on_table
        if not candidates:
            return None
        return sorted(candidates, key=lambda obj: obj.object_id)[0]

    def _build_instruction(self, target_object: ObjectInfo, scene: SceneSummary) -> str:
        """Build simple instruction for OpenVLA."""
        if target_object.category:
            obj_phrase = f"{target_object.category} object"
        else:
            obj_phrase = f"object {target_object.object_id}"
        return f"pick up the {obj_phrase} and place it in the bin"

    def _get_camera_image(self, scene: SceneSummary) -> np.ndarray:
        """Use scene snapshot first, then camera provider, then blank fallback."""
        if scene.rgb_snapshot is not None:
            return scene.rgb_snapshot

        if self._camera is not None:
            if hasattr(self._camera, "render_camera"):
                try:
                    return self._camera.render_camera(self._camera_name)
                except Exception as exc:
                    logger.warning("[OPENVLA] camera render failed: %s", exc)

        return np.zeros((224, 224, 3), dtype=np.uint8)

    def _build_proposal(
        self,
        action: OpenVLAAction,
        target_object: ObjectInfo,
        scene: SceneSummary,
    ) -> IntentProposal:
        """Wrap OpenVLA output into IntentProposal contract."""
        grip_state = "close" if action.gripper < 0.5 else "open"
        description = (
            f"OpenVLA trajectory for object {target_object.object_id} "
            f"(dx={action.delta_position[0]:.3f}, "
            f"dy={action.delta_position[1]:.3f}, "
            f"dz={action.delta_position[2]:.3f}, grip={grip_state})"
        )

        return IntentProposal(
            action=ActionType.CLEAN_TABLE,
            description=description,
            source="openvla",
            confidence=float(action.confidence),
            metadata={
                "primitive_type": PrimitiveType.OPENVLA_TRAJECTORY.value,
                "instruction": action.instruction,
                "target_object_id": target_object.object_id,
                "target_pos_xyz": list(target_object.pos_xyz),
                "delta_position": action.delta_position.tolist(),
                "delta_rotation": action.delta_rotation.tolist(),
                "gripper": float(action.gripper),
                "raw_action": action.raw_action.tolist(),
                "frame": scene.timestamp_frame,
            },
            suggested_object_ids=[target_object.object_id],
        )

    def _fallback_signal(self, reason: str) -> IntentProposal:
        """
        Return failure signal compatible with registry fallback behavior.

        Registry interprets IDLE + confidence=0.0 as "try next proposer".
        """
        return IntentProposal(
            action=ActionType.IDLE,
            description=f"OpenVLA unavailable: {reason}",
            source="openvla",
            confidence=0.0,
            metadata={"openvla_fallback_reason": reason},
        )

    @property
    def last_action(self) -> Optional[OpenVLAAction]:
        return self._last_action

    @property
    def proposal_count(self) -> int:
        return self._proposal_count

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def stats(self) -> dict:
        total = self._proposal_count + self._failure_count
        success_rate = (self._proposal_count / total) if total > 0 else 0.0
        return {
            "proposals": self._proposal_count,
            "failures": self._failure_count,
            "success_rate": success_rate,
            "enabled": self._enabled,
            "model_loaded": bool(getattr(self._adapter, "is_loaded", False)),
        }
