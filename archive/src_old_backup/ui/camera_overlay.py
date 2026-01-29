"""Camera Overlay - Visual overlay for camera feed."""

import cv2
import numpy as np
from typing import Optional
from intent_core.schema import SystemState
from vision.camera_scope_controller import CameraScopeSignal
from vision.object_detector import DetectionResult
from vision.tracking_schema import TrackingResult


class CameraOverlay:
    """
    Visual overlay for camera feed (ENHANCED for Week 7).
    
    Renders:
    - Center reticle (always visible)
    - Scoped object (yellow box)
    - All detections (optional, gray boxes)
    - Status banner (color-coded)
    - Multi-object indicators (NEW Week 7):
      - Suppressed objects (red X)
      - Ambiguous objects (yellow dashed)
      - Non-primary tracks (faint gray)
    - Pause banner (NEW Week 7)
    """
    
    def __init__(self, config: dict):
        """
        Initialize camera overlay.
        
        Args:
            config: Overlay configuration
        """
        self.show_reticle = config.get('show_reticle', True)
        self.show_all_detections = config.get('show_all_detections', False)
        self.bbox_color_scoped = (255, 255, 0)  # Yellow (BGR)
        self.bbox_color_detected = (128, 128, 128)  # Gray (BGR)
        self.bbox_thickness = 3
        self.reticle_radius = config.get('reticle_radius', 50)
    
    def render(self,
               frame: np.ndarray,
               scope_signal: Optional[CameraScopeSignal],
               detection_result: Optional[DetectionResult],
               tracking_result: Optional[TrackingResult],
               system_state: SystemState,
               gesture_data: Optional[dict] = None) -> np.ndarray:
        """
        Enhanced rendering with tracking visualization (Week 2) + gesture overlay (Week 4)
        
        Args:
            frame: Camera frame (BGR format)
            scope_signal: Current scope signal (if any)
            detection_result: Detection result (if any)
            tracking_result: Tracking result (if any)
            system_state: Current system state
            gesture_data: Gesture detection data (Week 4)
            
        Returns:
            Annotated frame (BGR format)
        """
        annotated = frame.copy()
        frame_h, frame_w = frame.shape[:2]
        
        # 1. Draw center reticle (always visible)
        if self.show_reticle:
            center = (frame_w // 2, frame_h // 2)
            cv2.circle(annotated, center, self.reticle_radius,
                      (255, 255, 255), 2)
            cv2.line(annotated,
                    (center[0] - 20, center[1]),
                    (center[0] + 20, center[1]),
                    (255, 255, 255), 2)
            cv2.line(annotated,
                    (center[0], center[1] - 20),
                    (center[0], center[1] + 20),
                    (255, 255, 255), 2)
        
        # 2. Draw all active tracks (faint gray) - Week 2
        if tracking_result:
            for obj in tracking_result.tracked_objects:
                x, y, w, h = obj.bbox
                # Faint gray box for all tracks
                cv2.rectangle(annotated, (x, y), (x + w, y + h),
                             (100, 100, 100), 1)
                # Track ID label (last 4 chars)
                track_id_short = obj.track_id[-4:] if len(obj.track_id) >= 4 else obj.track_id
                cv2.putText(annotated, f"T{track_id_short}",
                           (x, max(y - 5, 15)),
                           cv2.FONT_HERSHEY_SIMPLEX,
                           0.4, (100, 100, 100), 1)
        
        # 3. Draw all detections (optional, for debugging)
        if self.show_all_detections and detection_result:
            for obj in detection_result.objects:
                x, y, w, h = obj.bbox
                cv2.rectangle(annotated, (x, y), (x + w, y + h),
                            self.bbox_color_detected, 1)
        
        # 4. Draw candidate (blue dashed) if building stability - Week 2
        if scope_signal and scope_signal.tracking_metadata:
            metadata = scope_signal.tracking_metadata
            stability_counter = metadata.get('stability_counter', 0)
            
            if stability_counter > 0 and not scope_signal.scoped_object_id:
                # Candidate exists but not stable yet
                # Find candidate bbox from tracking result
                if tracking_result and scope_signal.tracking_metadata.get('candidate_track_id'):
                    candidate_id = scope_signal.tracking_metadata.get('candidate_track_id')
                    for obj in tracking_result.tracked_objects:
                        if obj.track_id == candidate_id:
                            x, y, w, h = obj.bbox
                            # Draw dashed blue box (approximate with multiple small rectangles)
                            dash_length = 5
                            gap_length = 3
                            # Top edge
                            for i in range(0, w, dash_length + gap_length):
                                end_x = min(x + i + dash_length, x + w)
                                cv2.line(annotated, (x + i, y), (end_x, y), (255, 0, 0), 2)
                            # Bottom edge
                            for i in range(0, w, dash_length + gap_length):
                                end_x = min(x + i + dash_length, x + w)
                                cv2.line(annotated, (x + i, y + h), (end_x, y + h), (255, 0, 0), 2)
                            # Left edge
                            for i in range(0, h, dash_length + gap_length):
                                end_y = min(y + i + dash_length, y + h)
                                cv2.line(annotated, (x, y + i), (x, end_y), (255, 0, 0), 2)
                            # Right edge
                            for i in range(0, h, dash_length + gap_length):
                                end_y = min(y + i + dash_length, y + h)
                                cv2.line(annotated, (x + w, y + i), (x + w, end_y), (255, 0, 0), 2)
                            
                            # Candidate label
                            cv2.putText(annotated, f"CANDIDATE ({stability_counter})",
                                       (x, max(y - 10, 20)),
                                       cv2.FONT_HERSHEY_SIMPLEX,
                                       0.5, (255, 0, 0), 2)
                            break
        
        # 5. Draw stable scope (solid yellow) - Week 2
        if scope_signal and scope_signal.scoped_object_id and scope_signal.bbox:
            x, y, w, h = scope_signal.bbox
            cv2.rectangle(annotated, (x, y), (x + w, y + h),
                         self.bbox_color_scoped,
                         self.bbox_thickness)
            
            # Label above bbox
            label_text = f"{scope_signal.object_label} ({scope_signal.confidence:.2f})"
            cv2.putText(annotated, label_text,
                       (x, max(y - 10, 20)),
                       cv2.FONT_HERSHEY_SIMPLEX,
                       0.6, self.bbox_color_scoped, 2)
            
            # Stability indicator - Week 2
            if scope_signal.tracking_metadata:
                stability = scope_signal.tracking_metadata.get('stability_counter', 0)
                if stability > 0:
                    cv2.putText(annotated, f"STABLE ({stability})",
                               (x, max(y - 25, 5)),
                               cv2.FONT_HERSHEY_SIMPLEX,
                               0.6, (0, 255, 255), 2)
        
        # 6. Warning overlays - Week 2
        if scope_signal and scope_signal.tracking_metadata:
            warnings = []
            metadata = scope_signal.tracking_metadata
            
            if metadata.get('oscillation_detected'):
                warnings.append("OSCILLATION - waiting for stability")
            if scope_signal.ambiguity_detected:
                warnings.append("AMBIGUITY - multiple candidates")
            if metadata.get('switch_blocked'):
                warnings.append("SWITCH BLOCKED - commitment active")
            
            # Draw warnings at bottom
            for i, warning in enumerate(warnings):
                y_pos = frame_h - 60 + i * 30
                cv2.putText(annotated, warning,
                           (10, y_pos),
                           cv2.FONT_HERSHEY_SIMPLEX,
                           0.7, (0, 0, 255), 2)
        
        # 7. Gesture overlay (NEW - Week 4)
        if gesture_data:
            self._draw_gesture_overlay(annotated, gesture_data)
        
        # 8. Status banner (top of frame)
        self._draw_status_banner(annotated, system_state, scope_signal)
        
        return annotated
    
    def _draw_gesture_overlay(self, frame: np.ndarray, gesture_data: dict):
        """
        Draw gesture indicators on camera frame (Week 4)
        
        Shows:
        - Progress bar for pinch confirmation
        - Block warnings
        """
        frame_h, frame_w = frame.shape[:2]
        
        # Draw progress bar for pinch
        if gesture_data.get('pinching'):
            frames_held = gesture_data.get('frames_held', 0)
            required = 6  # Could be configurable
            progress = min(1.0, frames_held / required)
            
            # Progress bar (top right)
            bar_width = 200
            bar_height = 30
            bar_x = frame_w - bar_width - 20
            bar_y = 60
            
            # Background
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height),
                         (50, 50, 50), -1)
            
            # Progress fill
            progress_width = int(bar_width * progress)
            if progress >= 1.0:
                color = (0, 255, 0)  # Green when complete
                text = "CONFIRMED"
            else:
                color = (0, 255, 255)  # Yellow/Cyan while building
                text = f"Pinch: {frames_held}/{required}"
            
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + progress_width, bar_y + bar_height),
                         color, -1)
            
            # Border
            cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height),
                         (255, 255, 255), 2)
            
            # Text
            cv2.putText(frame, text, (bar_x, bar_y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # Draw block warning
        gesture_blocked = gesture_data.get('blocked', False)
        if gesture_blocked:
            block_reason = gesture_data.get('block_reason', 'Unknown reason')
            # Draw at bottom left (above other warnings)
            y_pos = frame_h - 100
            cv2.putText(frame, f"Pinch ignored: {block_reason}",
                       (20, y_pos),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    
    def _draw_status_banner(self, frame: np.ndarray, state: SystemState, scope_signal: Optional[CameraScopeSignal]):
        """
        Draw system status at top of frame.
        
        Args:
            frame: Frame to draw on (modified in place)
            state: Current system state
            scope_signal: Current scope signal (if any)
        """
        banner_height = 40
        banner = np.zeros((banner_height, frame.shape[1], 3), dtype=np.uint8)
        
        # Background color based on state
        if state == SystemState.IDLE:
            banner[:] = (50, 50, 50)  # Gray (BGR)
            text = "IDLE"
        elif state == SystemState.SCOPED:
            banner[:] = (0, 100, 0)  # Dark green (BGR)
            if scope_signal and scope_signal.object_label:
                text = f"SCOPED: {scope_signal.object_label}"
            else:
                text = "SCOPED"
        elif state == SystemState.PAUSED:
            banner[:] = (0, 0, 100)  # Dark red (BGR)
            if scope_signal:
                reason = scope_signal.focus_reason[:50]  # Truncate if too long
                text = f"PAUSED: {reason}"
            else:
                text = "PAUSED"
        elif state == SystemState.CONFIRMING:
            banner[:] = (0, 150, 150)  # Cyan (BGR)
            text = "CONFIRMING"
        elif state == SystemState.EXECUTING:
            banner[:] = (0, 200, 0)  # Bright green (BGR)
            text = "EXECUTING"
        else:
            banner[:] = (50, 50, 50)
            text = str(state.value).upper()
        
        # Draw text
        cv2.putText(banner, text, (10, 25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                   (255, 255, 255), 2)
        
        # Overlay on frame
        frame[0:banner_height, :] = banner
    
    def render_with_snapshot(self,
                            frame: np.ndarray,
                            ui_snapshot: dict) -> np.ndarray:
        """
        Enhanced rendering with UI snapshot (NEW Week 7)
        
        Provides simpler interface for orchestrator - just pass snapshot.
        
        Args:
            frame: Camera frame
            ui_snapshot: Complete UI snapshot from orchestrator
            
        Returns:
            Annotated frame
        """
        # Extract relevant data from snapshot
        scope_signal = None  # Would need to reconstruct or pass separately
        detection_result = None
        tracking_result = ui_snapshot.get('tracking_result')
        
        # Get system state
        state_str = ui_snapshot.get('system_state', 'IDLE')
        try:
            system_state = SystemState[state_str.upper()]
        except (KeyError, AttributeError):
            system_state = SystemState.IDLE
        
        # Use existing render method as base
        annotated = self.render(
            frame=frame,
            scope_signal=scope_signal,
            detection_result=detection_result,
            tracking_result=tracking_result,
            system_state=system_state,
            gesture_data=ui_snapshot.get('gesture_data')
        )
        
        # Add Week 7 overlays
        if ui_snapshot.get('multi_object'):
            self._draw_multi_object_overlays(annotated, ui_snapshot)
        
        if ui_snapshot.get('recovery', {}).get('paused'):
            self._draw_pause_banner(annotated, ui_snapshot)
        
        return annotated
    
    def _draw_multi_object_overlays(self, frame: np.ndarray, ui_snapshot: dict):
        """
        Draw multi-object indicators (NEW Week 7)
        
        Visual hierarchy:
        1. Suppressed objects: red X
        2. Non-primary objects: faint gray boxes (already drawn by base render)
        3. Ambiguous runner-up: yellow dashed box
        4. Primary focus: solid green/yellow box (already drawn by base render)
        """
        mo = ui_snapshot.get('multi_object', {})
        primary_id = mo.get('primary_id')
        ambiguity = mo.get('ambiguity_detected', False)
        
        # Get all candidates (if available)
        candidates = mo.get('candidates', [])
        if not candidates:
            return
        
        # Get oscillation info
        oscillation = ui_snapshot.get('oscillation', {})
        suppressed_ids = oscillation.get('suppressed_ids', [])
        
        for candidate in candidates:
            track_id = candidate.get('track_id')
            bbox = candidate.get('bbox')  # (x, y, w, h) if available
            label = candidate.get('label', 'object')
            rank = candidate.get('rank', 99)
            
            # Skip if no bbox (would need to get from tracking result)
            if not bbox:
                continue
            
            x, y, w, h = bbox
            
            # Check if suppressed
            if track_id in suppressed_ids:
                # Suppressed: red X
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
                cv2.line(frame, (x, y), (x + w, y + h), (0, 0, 255), 3)
                cv2.line(frame, (x + w, y), (x, y + h), (0, 0, 255), 3)
                cv2.putText(frame, "SUPPRESSED", (x, max(y - 10, 15)),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            
            elif track_id == primary_id:
                # Primary: solid green/yellow (handled by base render)
                pass
            
            elif ambiguity and rank == 2:
                # Runner-up in ambiguous situation: yellow dashed
                self._draw_dashed_rect(frame, (x, y), (x + w, y + h), (0, 255, 255), 2)
                cv2.putText(frame, f"{label} (ambiguous)", (x, max(y - 10, 15)),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
            
            # Note: Other objects already drawn as faint gray in base render
        
        # Ambiguity warning (center of frame)
        if ambiguity:
            h, w = frame.shape[:2]
            cv2.putText(frame, "⚠ AMBIGUITY - WAITING", (w // 2 - 150, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        # Oscillation warning
        if oscillation.get('oscillating'):
            h, w = frame.shape[:2]
            cv2.putText(frame, "⚠ OSCILLATION - SUPPRESSING", (w // 2 - 200, 80),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    
    def _draw_pause_banner(self, frame: np.ndarray, ui_snapshot: dict):
        """
        Draw prominent pause banner (ENHANCED Week 8)
        
        Now shows:
        - Top banner: Pause status with trigger and reason
        - Bottom banner: Recovery hint
        - Reference to sidebar for detailed steps
        """
        recovery = ui_snapshot.get('recovery', {})
        trigger = recovery.get('trigger', 'unknown')
        reason = recovery.get('reason', 'System paused')
        
        h, w = frame.shape[:2]
        
        # === TOP BANNER: Pause Status ===
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 100), (0, 0, 180), -1)  # Dark red background (BGR)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
        
        # Title
        cv2.putText(frame, "SYSTEM PAUSED", (20, 35),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
        
        # Trigger
        trigger_label = trigger.replace('_', ' ').title()
        cv2.putText(frame, f"Trigger: {trigger_label}", (20, 65),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 200, 100), 2)
        
        # Reason (truncated if too long)
        reason_short = reason[:50] + "..." if len(reason) > 50 else reason
        cv2.putText(frame, reason_short, (20, 90),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # === BOTTOM BANNER: Recovery Hint ===
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, h - 60), (w, h), (50, 50, 150), -1)  # Dark blue background (BGR)
        cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
        
        # Hint
        hint = self._get_recovery_hint(trigger)
        cv2.putText(frame, hint, (20, h - 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        
        # Reference to sidebar
        cv2.putText(frame, "See sidebar for detailed recovery steps", (20, h - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    
    def _get_recovery_hint(self, trigger: str) -> str:
        """
        Get brief recovery hint for trigger (NEW Week 8)
        
        Args:
            trigger: Pause trigger identifier
            
        Returns:
            Brief recovery hint string
        """
        hints = {
            'object_loss': "Recovery: Bring object back into view",
            'hand_loss': "Recovery: Show hand to camera",
            'ambiguity_during_confirm': "Recovery: Move objects apart for clarity",
            'confidence_drop': "Recovery: Improve object visibility",
            'attention_timeout': "Recovery: Resume interaction with system",
            'state_uncertainty': "Recovery: Wait for clear state",
            'scope_drift': "Recovery: Keep object centered and stable",
            'oscillation': "Recovery: Focus on one object"
        }
        return hints.get(trigger, "Recovery: See sidebar for instructions")
    
    def _draw_dashed_rect(self, frame: np.ndarray, pt1: tuple, pt2: tuple, 
                         color: tuple, thickness: int):
        """
        Draw dashed rectangle (helper for Week 7)
        
        Args:
            frame: Frame to draw on
            pt1: Top-left corner (x, y)
            pt2: Bottom-right corner (x, y)
            color: BGR color tuple
            thickness: Line thickness
        """
        x1, y1 = pt1
        x2, y2 = pt2
        
        dash_length = 10
        gap_length = 5
        
        # Top edge
        for x in range(x1, x2, dash_length + gap_length):
            cv2.line(frame, (x, y1), (min(x + dash_length, x2), y1), color, thickness)
        
        # Bottom edge
        for x in range(x1, x2, dash_length + gap_length):
            cv2.line(frame, (x, y2), (min(x + dash_length, x2), y2), color, thickness)
        
        # Left edge
        for y in range(y1, y2, dash_length + gap_length):
            cv2.line(frame, (x1, y), (x1, min(y + dash_length, y2)), color, thickness)
        
        # Right edge
        for y in range(y1, y2, dash_length + gap_length):
            cv2.line(frame, (x2, y), (x2, min(y + dash_length, y2)), color, thickness)

