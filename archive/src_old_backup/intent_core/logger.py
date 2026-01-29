"""Event Logger - Logs camera events for replay and analysis."""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import logging

from intent_core.schema import CameraEventType
from vision.camera_stream import CameraFrame
from vision.object_detector import DetectionResult
from vision.focus_selector import FocusResult
from vision.camera_scope_controller import CameraScopeSignal
from vision.tracking_schema import TrackingResult
from vision.scope_stability import StableScopeResult
from vision.focus_commitment import CommitmentResult
from affordances.affordance_schema import AffordanceSet
from affordances.state_schema import ObjectStateEstimate
from vision.hand_detector import HandDetectionResult
from vision.pinch_detector import PinchObservation
from vision.pinch_stability import PinchState
from vision.gesture_confirm_controller import GestureConfirmSignal
from execution.action_schema import ActionRequest, ExecutionResult
from execution.action_history import ActionRecord
from affordances.option_selector import HighlightedOption

logger = logging.getLogger(__name__)

# Week 8: Import recovery types for narrative logging
try:
    from src.vision.recovery_controller import RecoveryPlan, PauseTrigger, RecoveryAction
except ImportError:
    # Graceful degradation if recovery not available
    RecoveryPlan = None
    PauseTrigger = None
    RecoveryAction = None


class EventLogger:
    """
    Event logger for camera pipeline events.
    
    Logs events in JSON format (one per line) for replay and analysis.
    Critical for replay:
    - Log enough data to recreate decisions
    - Do NOT log raw image data (too large)
    - Log detection IDs for correlation
    - Log timestamps for temporal analysis
    """
    
    def __init__(self, log_file: Optional[str] = None, enabled: bool = True):
        """
        Initialize event logger.
        
        Args:
            log_file: Path to log file (if None, uses default)
            enabled: Whether logging is enabled
        """
        self.enabled = enabled
        
        if not self.enabled:
            logger.info("EventLogger: Logging disabled")
            return
        
        if log_file is None:
            # Default log file location
            log_dir = Path("data/logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = str(log_dir / f"camera_events_{timestamp}.jsonl")
        
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Open file in append mode
        self._file_handle = open(self.log_file, 'a')
        logger.info(f"EventLogger: Logging to {self.log_file}")
    
    def _write_event(self, event: Dict[str, Any]):
        """
        Write event to log file.
        
        Args:
            event: Event dictionary to log
        """
        if not self.enabled:
            return
        
        try:
            # Write as JSON line (JSONL format)
            json_line = json.dumps(event, default=str)
            self._file_handle.write(json_line + '\n')
            self._file_handle.flush()  # Ensure immediate write
        except Exception as e:
            logger.error(f"EventLogger: Failed to write event: {e}")
    
    def log_camera_frame(self, frame: CameraFrame):
        """
        Log frame metadata (not image data).
        
        Args:
            frame: Camera frame to log
        """
        self._write_event({
            "type": CameraEventType.FRAME_PROCESSED.value,
            "timestamp": frame.timestamp,
            "frame_id": frame.frame_id,
            "width": frame.width,
            "height": frame.height,
            "fps": frame.fps
        })
    
    def log_detection(self, result: DetectionResult):
        """
        Log detection results.
        
        Args:
            result: Detection result to log
        """
        self._write_event({
            "type": CameraEventType.DETECTION_RUN.value,
            "timestamp": result.timestamp,
            "frame_id": result.frame_id,
            "num_objects": len(result.objects),
            "objects": [
                {
                    "id": obj.detection_id,
                    "label": obj.label,
                    "bbox": obj.bbox,
                    "confidence": obj.confidence,
                    "center": obj.center_point,
                    "area": obj.area
                }
                for obj in result.objects
            ],
            "detection_time_ms": result.detection_time_ms
        })
    
    def log_focus_selection(self, result: FocusResult):
        """
        Log focus selection decision.
        
        Args:
            result: Focus result to log
        """
        self._write_event({
            "type": CameraEventType.FOCUS_SELECTED.value,
            "timestamp": result.timestamp,
            "primary_object_id": result.primary_object.track_id if result.primary_object else None,
            "primary_object_label": result.primary_object.label if result.primary_object else None,
            "ambiguity_detected": result.ambiguity_detected,
            "ambiguity_reason": result.ambiguity_reason,
            "reason": result.reason,
            "num_candidates_considered": result.num_candidates_considered,
            "score_margin": result.score_margin,
            "runner_up_id": result.runner_up_object.track_id if result.runner_up_object else None
        })
    
    def log_camera_scope_signal(self, signal: CameraScopeSignal):
        """
        Log scope signal sent to core system.
        
        Args:
            signal: Scope signal to log
        """
        self._write_event({
            "type": CameraEventType.SCOPE_SIGNAL_EMITTED.value,
            "timestamp": signal.timestamp,
            "frame_id": signal.frame_id,
            "scoped_object_id": signal.scoped_object_id,
            "object_label": signal.object_label,
            "confidence": signal.confidence,
            "focus_reason": signal.focus_reason,
            "ambiguity_detected": signal.ambiguity_detected,
            "suggested_state": signal.suggested_state.value
        })
    
    def log_ambiguity_detected(self, 
                               frame_id: int,
                               timestamp: float,
                               reason: str,
                               candidates: Optional[list] = None):
        """
        Log ambiguity detection event.
        
        Args:
            frame_id: Frame ID where ambiguity was detected
            timestamp: Timestamp of detection
            reason: Reason for ambiguity
            candidates: Optional list of candidate objects
        """
        event = {
            "type": CameraEventType.AMBIGUITY_DETECTED.value,
            "timestamp": timestamp,
            "frame_id": frame_id,
            "reason": reason
        }
        
        if candidates:
            event["candidates"] = [
                {
                    "id": c.detection_id if hasattr(c, 'detection_id') else None,
                    "label": c.label if hasattr(c, 'label') else None,
                    "confidence": c.confidence if hasattr(c, 'confidence') else None
                }
                for c in candidates
            ]
        
        self._write_event(event)
    
    def log_tracking_result(self, result: TrackingResult):
        """
        Log tracking state.
        
        Args:
            result: Tracking result to log
        """
        self._write_event({
            "type": "tracking_update",
            "timestamp": result.timestamp,
            "frame_id": result.frame_id,
            "num_active_tracks": result.num_active_tracks,
            "num_confirmed_tracks": result.num_confirmed_tracks,
            "num_new_tracks": result.num_new_tracks,
            "num_deleted_tracks": result.num_deleted_tracks,
            "tracked_objects": [
                {
                    "track_id": obj.track_id,
                    "label": obj.label,
                    "bbox": obj.bbox,
                    "confidence": obj.confidence,
                    "age_frames": obj.age_frames,
                    "hits": obj.hits,
                    "confirmed": obj.confirmed
                }
                for obj in result.tracked_objects
            ]
        })
    
    def log_stability_check(self, result: StableScopeResult):
        """
        Log scope stability validation.
        
        Args:
            result: Stability result to log
        """
        self._write_event({
            "type": "stability_check",
            "timestamp": result.timestamp,
            "stable": result.stable,
            "scoped_track_id": result.scoped_track_id,
            "candidate_track_id": result.candidate_track_id,
            "stability_counter": result.stability_counter,
            "required_frames": result.required_frames,
            "reason": result.reason,
            "ambiguity": result.ambiguity
        })
    
    def log_commitment_check(self, result: CommitmentResult):
        """
        Log focus commitment decision.
        
        Args:
            result: Commitment result to log
        """
        self._write_event({
            "type": "commitment_check",
            "commitment_active": result.commitment_active,
            "switch_blocked": result.switch_blocked,
            "oscillation_detected": result.oscillation_detected,
            "allowed_primary_id": result.allowed_primary.track_id if result.allowed_primary else None,
            "reason": result.reason
        })
    
    def log_state_estimate(self, estimate: ObjectStateEstimate):
        """
        Log state inference (Week 6)
        
        Critical for:
        - Transparency (how was state inferred?)
        - Debugging (confidence thresholds, evidence)
        - Replay (deterministic state estimation)
        
        Args:
            estimate: State estimate to log
        """
        self._write_event({
            "type": "state_estimate",
            "timestamp": estimate.timestamp,
            "frame_id": estimate.frame_id,
            "object_id": estimate.object_id,
            "category": estimate.category,
            "state": estimate.state,
            "confidence": estimate.confidence,
            "method": estimate.method,
            "reason": estimate.reason,
            "evidence": estimate.evidence,
            "uncertain": estimate.uncertain,
            "too_uncertain": estimate.too_uncertain
        })
    
    def log_affordance_set(self, affordance_set: AffordanceSet):
        """
        Log affordance computation (ENHANCED Week 6)
        
        Critical for:
        - Replay (deterministic affordance generation)
        - Transparency (why these options?)
        - Debugging (category classification, filtering)
        - State inference (NEW Week 6)
        
        Args:
            affordance_set: Affordance set to log
        """
        self._write_event({
            "type": "affordance_set",
            "timestamp": affordance_set.timestamp,
            "frame_id": affordance_set.frame_id,
            
            # Object context
            "object_id": affordance_set.object_id,
            "object_label": affordance_set.object_label,
            
            # Category
            "category": affordance_set.category.value,
            "category_confidence": affordance_set.category_confidence,
            
            # Options
            "num_options": len(affordance_set.options),
            "options": [
                {
                    "affordance_type": opt.affordance_type.value,
                    "title": opt.title,
                    "description": opt.description,
                    "risk": opt.risk.value,
                    "confidence": opt.confidence,
                    "reason": opt.reason,
                    "requires_confirmation": opt.requires_confirmation,
                    "metadata": opt.metadata
                }
                for opt in affordance_set.options
            ],
            
            # Blocking
            "blocked": affordance_set.blocked,
            "block_reason": affordance_set.block_reason,
            
            # Reasoning trail
            "reasoning": affordance_set.reasoning,
            
            # NEW Week 6: State inference info
            "state_inference": affordance_set.reasoning.get('state_estimate'),
            "state_aware": affordance_set.reasoning.get('state_aware', False)
        })
    
    def log_hand_detection(self, result: HandDetectionResult):
        """
        Log hand detection result (Week 4)
        
        Args:
            result: Hand detection result to log
        """
        self._write_event({
            "type": "hand_detection",
            "timestamp": result.timestamp,
            "frame_id": result.frame_id,
            "detected": result.detected,
            "confidence": result.confidence,
            "failure_reason": result.failure_reason,
            "landmarks": {
                "thumb_tip": result.landmarks.thumb_tip if result.landmarks else None,
                "index_tip": result.landmarks.index_tip if result.landmarks else None,
                "handedness": result.landmarks.handedness if result.landmarks else None
            } if result.detected else None
        })
    
    def log_pinch_observation(self, obs: PinchObservation):
        """
        Log pinch observation (Week 4)
        
        Args:
            obs: Pinch observation to log
        """
        self._write_event({
            "type": "pinch_observation",
            "timestamp": obs.timestamp,
            "frame_id": obs.frame_id,
            "pinching": obs.pinching,
            "distance_normalized": obs.distance,
            "distance_pixels": obs.distance_pixels,
            "confidence": obs.confidence,
            "threshold": obs.threshold_used
        })
    
    def log_pinch_state(self, state: PinchState):
        """
        Log pinch stability state (Week 4)
        
        Args:
            state: Pinch state to log
        """
        self._write_event({
            "type": "pinch_state",
            "timestamp": state.timestamp,
            "stable": state.stable,
            "confirmed": state.confirmed,
            "just_confirmed": state.just_confirmed,
            "frames_held": state.frames_held,
            "frames_released": state.frames_released,
            "reason": state.reason
        })
    
    def log_gesture_signal(self, signal: GestureConfirmSignal):
        """
        Log gesture confirmation signal (Week 4)
        
        Args:
            signal: Gesture confirmation signal to log
        """
        self._write_event({
            "type": "gesture_confirm_signal",
            "timestamp": signal.timestamp,
            "frame_id": signal.frame_id,
            "confirmed": signal.confirmed,
            "blocked": signal.blocked,
            "block_reason": signal.block_reason,
            "scoped_object_id": signal.scoped_object_id,
            "affordance_count": signal.affordance_count,
            "intent": {
                "type": signal.intent.type.value,
                "confidence": signal.intent.confidence,
                "source": signal.intent.source,
                "payload": signal.intent.payload
            } if signal.intent else None
        })
    
    def log_camera_failure(self,
                          frame_id: Optional[int],
                          timestamp: float,
                          error_type: str,
                          error_message: str):
        """
        Log camera failure event.
        
        Args:
            frame_id: Frame ID (if available)
            timestamp: Timestamp of failure
            error_type: Type of error (e.g., "camera_disconnected", "frame_read_error")
            error_message: Human-readable error message
        """
        self._write_event({
            "type": CameraEventType.CAMERA_FAILURE.value,
            "timestamp": timestamp,
            "frame_id": frame_id,
            "error_type": error_type,
            "error_message": error_message
        })
    
    def log_action_request(self, request: ActionRequest):
        """Log action request (before execution)"""
        self._write_event({
            "type": "action_request",
            "timestamp": request.timestamp,
            "action_id": request.action_id,
            "user_id": request.user_id,
            "session_id": request.session_id,
            "object_id": request.object_id,
            "object_label": request.object_label,
            "category": request.category,
            "action_type": request.action_type.value,
            "metadata": request.metadata,
            "authority_chain": request.authority_chain
        })
    
    def log_execution_result(self, result: ExecutionResult):
        """Log execution result (success or failure)"""
        self._write_event({
            "type": "execution_result" if result.ok else "execution_refused",
            "timestamp": result.timestamp,
            "action_id": result.action_id,
            "ok": result.ok,
            "reason": result.reason,
            "before_state": result.before_state,
            "after_state": result.after_state,
            "reversible": result.reversible,
            "execution_time_ms": result.execution_time_ms,
            "error_code": result.error_code,
            "error_details": result.error_details
        })
    
    def log_action_recorded(self, record: ActionRecord):
        """Log action recorded in history (for undo)"""
        self._write_event({
            "type": "action_recorded",
            "timestamp": record.timestamp,
            "action_id": record.action_id,
            "object_id": record.object_id,
            "object_label": record.object_label,
            "category": record.category,
            "action_type": record.action_type,
            "reversible": record.reversible,
            "expires_at": record.expires_at,
            "undo_window_seconds": record.expires_at - record.timestamp
        })
    
    def log_undo_available(self, action_record: ActionRecord, time_remaining: float):
        """Log that undo is available (ENHANCED Week 8 with narrative)"""
        self._write_event({
            "type": "undo_available",
            "timestamp": action_record.timestamp,
            "action_id": action_record.action_id,
            "object_id": action_record.object_id,
            "object_label": action_record.object_label,
            "action_type": action_record.action_type,
            "time_remaining": time_remaining,
            "expires_at": action_record.expires_at,
            
            # Narrative (NEW Week 8)
            "narrative": (f"Undo available for {action_record.action_type} on {action_record.object_label} "
                         f"for {time_remaining:.1f} more seconds")
        })
    
    def log_undo_request(self, success: bool, reason: str, timestamp: float):
        """Log undo request (ENHANCED Week 8 with narrative)"""
        self._write_event({
            "type": "undo_requested" if success else "undo_request_refused",
            "timestamp": timestamp,
            "success": success,
            "reason": reason,
            
            # Narrative (NEW Week 8)
            "narrative": f"Undo request {'accepted' if success else 'refused'}: {reason}"
        })
    
    def log_undo_confirm(self, result: ExecutionResult):
        """Log undo confirmation/execution (ENHANCED Week 8 with narrative)"""
        self._write_event({
            "type": "undo_applied" if result.ok else "undo_refused",
            "timestamp": result.timestamp,
            "action_id": result.action_id,
            "ok": result.ok,
            "reason": result.reason,
            "before_state": result.before_state,
            "after_state": result.after_state,
            
            # Narrative (NEW Week 8)
            "narrative": f"Undo {'applied' if result.ok else 'refused'}: {result.reason}"
        })
    
    def log_undo_cancelled(self, reason: str, timestamp: float):
        """Log undo cancellation (ENHANCED Week 8 with narrative)"""
        self._write_event({
            "type": "undo_cancelled",
            "timestamp": timestamp,
            "reason": reason,
            
            # Narrative (NEW Week 8)
            "narrative": f"Undo cancelled: {reason}"
        })
    
    # === Week 8: Pause & Recovery Narrative Logging ===
    
    def log_pause_triggered(self, plan):
        """
        Log pause trigger with complete narrative (NEW Week 8)
        
        Creates human-readable story of what happened
        
        Args:
            plan: RecoveryPlan object
        """
        if plan is None or RecoveryPlan is None:
            return
        
        self._write_event({
            "type": "pause_triggered",
            "timestamp": plan.timestamp,
            
            # What happened
            "trigger": plan.trigger.value if plan.trigger else None,
            "reason": plan.reason,
            "system_state_at_pause": plan.system_state_at_pause,
            
            # What was affected
            "cleared": {
                "scope": plan.clear_scope,
                "confirmation": plan.clear_confirmation,
                "execution": plan.clear_execution,
                "undo": plan.clear_undo
            },
            
            # What happens next
            "recovery_actions_required": [a.value for a in plan.recovery_actions],
            "recovery_explanation": plan.recovery_explanation,
            
            # Evidence (for debugging)
            "evidence": plan.evidence,
            
            # Narrative (human-readable story)
            "narrative": self._generate_pause_narrative(plan)
        })
    
    def _generate_pause_narrative(self, plan) -> str:
        """
        Generate human-readable narrative of pause event
        
        Example output:
        "System paused during CONFIRMING state because hand was lost.
         Confirmation was cancelled and no action was executed.
         To recover: ensure hand is visible, then re-confirm action."
        
        Args:
            plan: RecoveryPlan object
            
        Returns:
            Human-readable narrative string
        """
        trigger = plan.trigger.value if plan.trigger else "unknown"
        state = plan.system_state_at_pause
        reason = plan.reason
        
        # What was cleared
        cleared_items = []
        if plan.clear_scope:
            cleared_items.append("scope")
        if plan.clear_confirmation:
            cleared_items.append("confirmation")
        if plan.clear_execution:
            cleared_items.append("execution permission")
        if plan.clear_undo:
            cleared_items.append("undo availability")
        
        cleared_text = ", ".join(cleared_items) if cleared_items else "nothing"
        
        # Recovery steps
        if plan.recovery_actions:
            recovery_first_step = plan.recovery_actions[0].value.replace('_', ' ')
        else:
            recovery_first_step = "re-engage"
        
        narrative = (
            f"System paused during {state} state because of {trigger}: {reason}. "
            f"Cleared: {cleared_text}. "
            f"No action was executed. "
            f"To recover: {recovery_first_step}, then re-confirm."
        )
        
        return narrative
    
    def log_recovery_started(self, timestamp: float):
        """Log recovery process start (NEW Week 8)"""
        self._write_event({
            "type": "recovery_started",
            "timestamp": timestamp,
            "narrative": "User initiated recovery process"
        })
    
    def log_recovery_step_completed(self, step: str, timestamp: float):
        """Log recovery step completion (NEW Week 8)"""
        self._write_event({
            "type": "recovery_step_completed",
            "timestamp": timestamp,
            "step": step,
            "narrative": f"Recovery step completed: {step}"
        })
    
    def log_recovery_completed(self, timestamp: float):
        """Log successful recovery (NEW Week 8)"""
        self._write_event({
            "type": "recovery_completed",
            "timestamp": timestamp,
            "narrative": "Recovery completed successfully, system resumed normal operation"
        })
    
    def log_highlighted_option(self, highlighted: HighlightedOption):
        """Log which option is highlighted"""
        self._write_event({
            "type": "option_highlighted",
            "timestamp": highlighted.timestamp,
            "option_index": highlighted.option_index,
            "option_title": highlighted.option.title,
            "affordance_type": highlighted.option.affordance_type.value,
            "object_id": highlighted.affordance_set.object_id,
            "reason": highlighted.reason
        })
    
    def log_event(self, event: Dict[str, Any]):
        """
        Generic event logging method (Week 7+)
        
        Allows logging of custom events with arbitrary structure.
        Useful for orchestrator-level events.
        
        Args:
            event: Event dictionary to log
        """
        self._write_event(event)
    
    def close(self):
        """Close log file."""
        if self.enabled and hasattr(self, '_file_handle'):
            self._file_handle.close()
            logger.info("EventLogger: Log file closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

