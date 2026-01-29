"""System Orchestrator - Central coordinator for Week 1-9 system."""

from typing import Dict, Optional, List
import random
import logging

from intent_core.schema import SystemState, Intent, IntentType
from intent_core.logger import EventLogger
from vision.camera_stream import CameraStream, CameraConfig
from vision.object_detector import create_detector
from vision.camera_scope_controller import CameraScopeController
from ui.camera_overlay import CameraOverlay
from affordances.affordance_engine import AffordanceEngine
from vision.hand_detector import HandDetector
from vision.pinch_detector import PinchDetector
from vision.pinch_stability import PinchStability
from vision.gesture_confirm_controller import GestureConfirmController
from affordances.option_selector import OptionSelector, HighlightedOption
from execution.smart_world_sim import SmartWorldSim
from execution.action_executor import ActionExecutor
from execution.action_history import ActionHistory, ActionRecord
from execution.undo_controller import UndoController
from intent_core.router import Router
from intent_core.state_machine import StateMachine

# Week 7: Multi-Object Robustness + Failure Recovery
from vision.candidate_ranker import CandidateRanker
from vision.oscillation_detector import OscillationDetector
from vision.recovery_controller import RecoveryController, RecoveryPlan  # ENHANCED Week 8
from vision.tracking_schema import TrackedObject
from vision.video_session_logger import VideoSessionLogger

# Week 9: Final Demo Wrap-Up
from intent_core.ui_snapshot import UISnapshot
from intent_core.narrative_logger import NarrativeLogger
from intent_core.metrics_collector import MetricsCollector

import uuid
import time as time_module

logger = logging.getLogger(__name__)

class SystemOrchestrator:
    """
    Central orchestrator coordinating all components.
    
    This is a MINIMAL version for visual demo.
    Shows how the complete system would be wired.
    """
    
    def __init__(self, config: Dict, seed: int = 42):
        self.config = config
        self.tick_count = 0
        self.current_state = "IDLE"
        self.current_user = "user_A"
        self.current_scope = None
        
        # Simulated event history
        self.timeline_events = []
        
        # Random seed for determinism
        random.seed(config.get("seed", seed))
        
        # Event logger
        log_config = config.get("logging", {})
        self.logger = EventLogger(
            log_file=log_config.get("log_file"),
            enabled=log_config.get("enabled", True)
        )
        
        # Camera components (new)
        self.camera_enabled = config.get("camera_enabled", True)
        
        if self.camera_enabled:
            try:
                # Camera stream
                camera_config_dict = config.get("camera", {})
                camera_config = CameraConfig(
                    device_index=camera_config_dict.get("device_index", 0),
                    target_fps=camera_config_dict.get("target_fps", 30),
                    width=camera_config_dict.get("width", 640),
                    height=camera_config_dict.get("height", 480),
                    auto_exposure=camera_config_dict.get("auto_exposure", True),
                    mock_mode=camera_config_dict.get("mock_mode", True)  # Default to mock for demo
                )
                self.camera_stream = CameraStream(config=camera_config, seed=seed)
                
                # Start camera
                if not self.camera_stream.start():
                    logger.warning("SystemOrchestrator: Camera failed to start, disabling camera")
                    self.camera_enabled = False
                
                # Object detector
                self.object_detector = create_detector(
                    config.get("detection", {}),
                    seed=seed
                )
                
                # Camera scope controller (now includes tracking, focus, commitment, stability)
                # Pass full config so controller can access all sub-configs
                controller_config = {
                    **config.get("camera_scope_controller", {}),
                    "tracking": config.get("tracking", {}),
                    "focus_selection": config.get("focus_selection", {}),
                    "scope_stability": config.get("scope_stability", {}),
                    "focus_commitment": config.get("focus_commitment", {})
                }
                self.camera_scope_controller = CameraScopeController(
                    controller_config,
                    seed=seed
                )
                
                # Camera overlay
                self.camera_overlay = CameraOverlay(
                    config.get("camera_overlay", {})
                )
                
                logger.info("SystemOrchestrator: Camera pipeline initialized")
            except Exception as e:
                logger.error(f"SystemOrchestrator: Failed to initialize camera pipeline: {e}")
                self.camera_enabled = False
        
        # Camera state
        self.last_camera_frame = None
        self.last_scope_signal = None
        self.last_detection_result = None
        self.last_tracking_result = None
        
        # Affordance engine (NEW - Week 3)
        affordance_config = config.get('affordances', {})
        if affordance_config.get('enabled', False):
            try:
                self.affordance_engine = AffordanceEngine(
                    config=affordance_config,
                    seed=seed
                )
                self.affordances_enabled = True
                logger.info("SystemOrchestrator: Affordance engine initialized")
            except Exception as e:
                logger.error(f"SystemOrchestrator: Failed to initialize affordance engine: {e}")
                self.affordances_enabled = False
        else:
            self.affordances_enabled = False
        
        # Affordance state
        self.current_affordances = None
        
        # Gesture components (NEW - Week 4)
        gesture_config = config.get('gesture', {})
        if gesture_config.get('enabled', False):
            try:
                self.hand_detector = HandDetector(
                    config=gesture_config.get('hand_detection', {}),
                    seed=seed
                )
                self.pinch_detector = PinchDetector(
                    config=gesture_config.get('pinch_detection', {})
                )
                self.pinch_stability = PinchStability(
                    config=gesture_config.get('pinch_stability', {})
                )
                self.gesture_confirm_controller = GestureConfirmController(
                    config=gesture_config.get('confirmation_context', {})
                )
                self.gesture_enabled = True
                logger.info("SystemOrchestrator: Gesture pipeline initialized")
            except Exception as e:
                logger.error(f"SystemOrchestrator: Failed to initialize gesture pipeline: {e}")
                self.gesture_enabled = False
        else:
            self.gesture_enabled = False
        
        # Gesture state
        self.last_hand_detection = None
        self.last_pinch_observation = None
        self.last_pinch_state = None
        self.last_gesture_signal = None
        self.scope_stable_since_frame = None
        self._last_scope_id = None  # Track scope changes
        
        # === EXECUTION COMPONENTS (NEW - Week 5) ===
        execution_config = config.get('execution', {})
        if execution_config.get('enabled', False):
            try:
                self.execution_enabled = True
                
                # Smart world simulator
                self.world = SmartWorldSim(
                    config=execution_config.get('simulator', {}),
                    seed=seed
                )
                
                # Action executor
                self.action_executor = ActionExecutor(
                    config=execution_config,
                    world=self.world
                )
                
                # Action history (for undo)
                undo_config = config.get('undo', {})
                self.action_history = ActionHistory(
                    config=undo_config
                )
                
                # Undo controller
                self.undo_controller = UndoController(
                    config=undo_config,
                    history=self.action_history,
                    world=self.world
                )
                
                # Option selector
                self.option_selector = OptionSelector(
                    config=affordance_config.get('option_selector', {})
                )
                
                # Router (MODIFIED to actually execute)
                self.router = Router(
                    config=config.get('router', {}),
                    action_executor=self.action_executor
                )
                
                # State machine
                self.state_machine = StateMachine(
                    config=config.get('state_machine', {}),
                    undo_controller=self.undo_controller
                )
                
                logger.info("SystemOrchestrator: Execution pipeline initialized")
            except Exception as e:
                logger.error(f"SystemOrchestrator: Failed to initialize execution pipeline: {e}")
                self.execution_enabled = False
        else:
            self.execution_enabled = False
            # Create a simple state machine even if execution is disabled
            self.state_machine = StateMachine(
                config=config.get('state_machine', {}),
                undo_controller=None
            )
        
        # Execution state
        self.highlighted_option = None
        self.last_execution_result = None
        self.last_scope_id = None  # Track scope changes
        
        # === MULTI-OBJECT COMPONENTS (NEW - Week 7) ===
        multi_object_config = config.get('multi_object', {})
        if multi_object_config.get('enabled', True) and self.camera_enabled:
            try:
                self.multi_object_enabled = True
                
                # Candidate ranking
                self.candidate_ranker = CandidateRanker(
                    config=multi_object_config
                )
                
                # Oscillation detection
                self.oscillation_detector = OscillationDetector(
                    config=multi_object_config
                )
                
                logger.info("SystemOrchestrator: Multi-object robustness initialized")
            except Exception as e:
                logger.error(f"SystemOrchestrator: Failed to initialize multi-object components: {e}")
                self.multi_object_enabled = False
        else:
            self.multi_object_enabled = False
        
        # Multi-object state
        self.ranked_candidates = None
        self.oscillation_result = None
        
        # === FAILURE RECOVERY COMPONENTS (NEW - Week 7) ===
        robustness_config = config.get('robustness', {})
        if robustness_config.get('enabled', True):
            try:
                self.robustness_enabled = True
                
                # Recovery controller (manages all failure detectors)
                self.recovery_controller = RecoveryController(
                    config=robustness_config
                )
                
                logger.info("SystemOrchestrator: Failure recovery initialized")
            except Exception as e:
                logger.error(f"SystemOrchestrator: Failed to initialize recovery components: {e}")
                self.robustness_enabled = False
        else:
            self.robustness_enabled = False
        
        # Recovery state (ENHANCED Week 8)
        self.last_recovery_plan: Optional[RecoveryPlan] = None
        self.recovery_active = False
        
        # === VIDEO SESSION LOGGING (NEW - Week 7) ===
        video_session_config = config.get('video_session', {})
        if video_session_config.get('enabled', True):
            try:
                # Generate unique session ID
                session_id = str(uuid.uuid4().hex[:8])
                
                self.video_logger = VideoSessionLogger(
                    config=video_session_config,
                    session_id=session_id
                )
                
                logger.info(f"SystemOrchestrator: Video session logger initialized (session_id={session_id})")
            except Exception as e:
                logger.error(f"SystemOrchestrator: Failed to initialize video logger: {e}")
                self.video_logger = None
        else:
            self.video_logger = None
        
        # === WEEK 9 COMPONENTS (Final Demo Wrap-Up) ===
        # Narrative logger - Human-readable event tracking
        narrative_config = config.get('narrative', {})
        self.narrative_logger = NarrativeLogger(narrative_config)
        logger.info("SystemOrchestrator: Narrative logger initialized")
        
        # Metrics collector - Quantitative safety proof
        self.metrics_collector = MetricsCollector()
        logger.info("SystemOrchestrator: Metrics collector initialized")
        
        # Session start time for UISnapshot
        self.session_start_time = time_module.time()
        self.frame_id_counter = 0
        
        logger.info("SystemOrchestrator: Week 9 components initialized")
    
    def step(self, timestamp: Optional[float] = None) -> UISnapshot:
        """
        Execute one system tick (FINALIZED for Week 9)
        
        Pipeline order:
        1. Camera + tracking (Week 1-2)
        2. Multi-object ranking (Week 7)
        3. Oscillation detection (Week 7)
        4. Affordance computation (Week 3-6)
        5. Option highlighting (Week 5)
        6. Gesture detection (Week 4)
        7. Failure detection (Week 7-8)
        8. Intent pipeline + execution (Week 4-5)
        9. Undo management (Week 5)
        10. UI update (Week 9 - UISnapshot with authority gates, narrative, metrics)
        
        Returns:
            UISnapshot: Complete UI state for this frame
        """
        if timestamp is None:
            timestamp = self.tick_count * 0.1
        
        self.tick_count += 1
        
        # === CAMERA PIPELINE (Week 1-2) ===
        if self.camera_enabled:
            try:
                self._camera_tick(timestamp)
            except Exception as e:
                logger.error(f"SystemOrchestrator: Camera tick failed: {e}")
                # Camera failure does NOT crash system - continue without camera
                self.camera_enabled = False
        
        # === MULTI-OBJECT ROBUSTNESS (NEW - Week 7) ===
        if self.multi_object_enabled:
            try:
                self._multi_object_tick(timestamp)
            except Exception as e:
                logger.error(f"SystemOrchestrator: Multi-object tick failed: {e}")
                # Multi-object failure does NOT crash system
                self.multi_object_enabled = False
        
        # === AFFORDANCE PIPELINE (Week 3-6) ===
        if self.affordances_enabled:
            try:
                self._affordance_tick(timestamp)
            except Exception as e:
                logger.error(f"SystemOrchestrator: Affordance tick failed: {e}")
                # Affordance failure does NOT crash system - continue without affordances
                self.affordances_enabled = False
        
        # === OPTION HIGHLIGHTING (Week 5) ===
        if self.execution_enabled:
            try:
                self._option_highlighting_tick(timestamp)
            except Exception as e:
                logger.error(f"SystemOrchestrator: Option highlighting tick failed: {e}")
        
        # === GESTURE PIPELINE (Week 4) ===
        if self.gesture_enabled:
            try:
                self._gesture_tick(timestamp)
            except Exception as e:
                logger.error(f"SystemOrchestrator: Gesture tick failed: {e}")
                # Gesture failure does NOT crash system - continue without gestures
                self.gesture_enabled = False
        
        # === FAILURE RECOVERY (NEW - Week 7) ===
        if self.robustness_enabled:
            try:
                self._robustness_tick(timestamp)
            except Exception as e:
                logger.error(f"SystemOrchestrator: Robustness tick failed: {e}")
                # Recovery failure does NOT crash system
                self.robustness_enabled = False
        
        # === INTENT PIPELINE (MODIFIED for execution) ===
        try:
            self._intent_tick(timestamp)
        except Exception as e:
            logger.error(f"SystemOrchestrator: Intent tick failed: {e}")
        
        # === UNDO MANAGEMENT (NEW - Week 5) ===
        if self.execution_enabled:
            try:
                self._undo_tick(timestamp)
            except Exception as e:
                logger.error(f"SystemOrchestrator: Undo tick failed: {e}")
        
        # === UI UPDATE (ENHANCED Week 9) ===
        # Build complete UISnapshot with all system state
        ui_snapshot = self._build_ui_snapshot(timestamp)
        
        # === VIDEO SESSION LOGGING (NEW - Week 7) ===
        # Convert to dict for legacy logging
        if self.video_logger:
            try:
                self.video_logger.log_frame(ui_snapshot.to_dict())
            except Exception as e:
                logger.error(f"SystemOrchestrator: Video logging failed: {e}")
        
        return ui_snapshot
    
    def _simulate_state_transition(self, timestamp: float):
        """Simulate realistic state transitions."""
        
        # Only simulate if state machine not available (backward compatibility)
        if not self.state_machine:
            # Simple state machine simulation
            if self.tick_count % 10 == 0:
                # Every 10 ticks, change state
                states = ["IDLE", "SCOPED", "CONFIRMING", "EXECUTING", "PAUSED"]
                self.current_state = random.choice(states)
                
                # Add to timeline
                self.timeline_events.append({
                    "timestamp": timestamp,
                    "intent_type": random.choice(["SELECT", "CONFIRM", "IDLE"]),
                    "target": random.choice(["obj_left", "obj_center", "obj_right", ""]),
                    "confidence": random.uniform(0.7, 0.95),
                    "result": self.current_state
                })
                
                # Keep only last 10 events
                if len(self.timeline_events) > 10:
                    self.timeline_events.pop(0)
        else:
            # Use real state machine state
            if self.state_machine:
                self.current_state = self.state_machine.current_state.value
    
    def _camera_tick(self, timestamp: float):
        """
        Process one camera frame
        
        Pipeline:
        Frame → Detection → Focus Selection → Scope Signal → (Log Everything)
        """
        
        # 1. Get frame
        frame = self.camera_stream.get_frame()
        if frame is None:
            # Camera unavailable - log and continue
            self.logger.log_camera_failure(
                frame_id=None,
                timestamp=timestamp,
                error_type="no_frame_available",
                error_message="Camera stream returned None"
            )
            return
        
        self.last_camera_frame = frame
        self.logger.log_camera_frame(frame)
        
        # 2. Detect objects
        detection_result = self.object_detector.detect(frame)
        self.last_detection_result = detection_result
        self.logger.log_detection(detection_result)
        
        # 3. Process through full tracking pipeline (Week 2)
        # Controller now handles: Tracking → Focus → Commitment → Stability
        scope_signal = self.camera_scope_controller.process_frame(
            detection_result=detection_result,
            frame_width=frame.width,
            frame_height=frame.height,
            frame_id=frame.frame_id,
            timestamp=timestamp
        )
        self.last_scope_signal = scope_signal
        
        # Store tracking result for overlay visualization
        self.last_tracking_result = self.camera_scope_controller.last_tracking_result
        
        # Log Week 2 pipeline events
        if self.camera_scope_controller.last_tracking_result:
            self.logger.log_tracking_result(self.camera_scope_controller.last_tracking_result)
        
        if self.camera_scope_controller.last_focus_result:
            self.logger.log_focus_selection(self.camera_scope_controller.last_focus_result)
        
        if self.camera_scope_controller.last_commitment_result:
            self.logger.log_commitment_check(self.camera_scope_controller.last_commitment_result)
        
        if self.camera_scope_controller.last_stability_result:
            self.logger.log_stability_check(self.camera_scope_controller.last_stability_result)
        
        self.logger.log_camera_scope_signal(scope_signal)
        
        # 5. Feed into core system (SUGGESTION ONLY)
        self._apply_camera_scope_to_system(scope_signal)
    
    def _affordance_tick(self, timestamp: float):
        """
        Compute affordances for current scope (NEW - Week 3)
        
        CRITICAL: This does NOT trigger execution
        Affordances are display-only suggestions
        """
        
        # Get current scope from camera pipeline
        scoped_object = None
        ambiguity = False
        
        if self.last_scope_signal:
            # Check if we have a stable scope
            if (self.last_scope_signal.scoped_object_id and
                self.last_scope_signal.suggested_state == SystemState.SCOPED):
                # We need the actual TrackedObject
                # Get it from the tracker
                if (self.camera_scope_controller and 
                    hasattr(self.camera_scope_controller, 'tracker') and
                    self.camera_scope_controller.tracker):
                    track = self.camera_scope_controller.tracker.get_track(
                        self.last_scope_signal.scoped_object_id
                    )
                    if track:
                        from src.vision.tracking_schema import TrackedObject
                        scoped_object = TrackedObject.from_track(track)
            
            # Check ambiguity from camera signal
            ambiguity = self.last_scope_signal.ambiguity_detected
        
        # Compute affordances
        frame_id = self.last_camera_frame.frame_id if self.last_camera_frame else self.tick_count
        affordance_set = self.affordance_engine.compute(
            scoped_object=scoped_object,
            ambiguity=ambiguity,
            frame_id=frame_id,
            timestamp=timestamp,
            frame=self.last_camera_frame.image if self.last_camera_frame else None
        )
        
        # Store for UI
        self.current_affordances = affordance_set
        
        # Log (will add log_affordance_set method to logger)
        if hasattr(self.logger, 'log_affordance_set'):
            self.logger.log_affordance_set(affordance_set)
    
    def _gesture_tick(self, timestamp: float):
        """
        Process gesture detection for current frame (NEW - Week 4)
        
        Pipeline:
        1. Detect hand landmarks
        2. Detect pinch
        3. Check stability
        4. Validate context
        5. Generate CONFIRM intent (or block)
        """
        
        if not self.last_camera_frame:
            return
        
        frame = self.last_camera_frame.image
        frame_id = self.last_camera_frame.frame_id
        frame_width = self.last_camera_frame.width
        frame_height = self.last_camera_frame.height
        
        # 1. Detect hand
        hand_detection = self.hand_detector.detect(
            frame=frame,
            frame_id=frame_id,
            timestamp=timestamp
        )
        self.last_hand_detection = hand_detection
        
        # Log hand detection (will add log_hand_detection method)
        if hasattr(self.logger, 'log_hand_detection'):
            self.logger.log_hand_detection(hand_detection)
        
        # 2. Detect pinch
        pinch_observation = self.pinch_detector.observe(
            landmarks=hand_detection.landmarks if hand_detection.detected else None,
            frame_width=frame_width,
            frame_height=frame_height,
            frame_id=frame_id,
            timestamp=timestamp
        )
        self.last_pinch_observation = pinch_observation
        
        # Log pinch observation (will add log_pinch_observation method)
        if pinch_observation and hasattr(self.logger, 'log_pinch_observation'):
            self.logger.log_pinch_observation(pinch_observation)
        
        # 3. Check stability
        pinch_state = self.pinch_stability.step(
            observation=pinch_observation,
            timestamp=timestamp
        )
        self.last_pinch_state = pinch_state
        
        # Log pinch state (will add log_pinch_state method)
        if hasattr(self.logger, 'log_pinch_state'):
            self.logger.log_pinch_state(pinch_state)
        
        # 4. Track scope age
        current_scope_id = self.last_scope_signal.scoped_object_id if self.last_scope_signal else None
        
        # Reset if scope changed
        if current_scope_id != getattr(self, '_last_scope_id', None):
            self.scope_stable_since_frame = frame_id if current_scope_id else None
            self._last_scope_id = current_scope_id
        
        if current_scope_id and self.scope_stable_since_frame is not None:
            scope_age = frame_id - self.scope_stable_since_frame
        else:
            scope_age = 0
        
        # 5. Validate context and generate signal
        # Convert string state to SystemState enum
        system_state_enum = self._string_to_system_state(self.current_state)
        
        gesture_signal = self.gesture_confirm_controller.process(
            pinch_state=pinch_state,
            system_state=system_state_enum,
            scoped_object_id=current_scope_id,
            affordances=self.current_affordances,
            scope_age_frames=scope_age,
            ambiguity_detected=self.last_scope_signal.ambiguity_detected if self.last_scope_signal else False,
            frame_id=frame_id,
            timestamp=timestamp
        )
        self.last_gesture_signal = gesture_signal
        
        # Log gesture signal (will add log_gesture_signal method)
        if hasattr(self.logger, 'log_gesture_signal'):
            self.logger.log_gesture_signal(gesture_signal)
        
        # 6. Inject CONFIRM intent if confirmed
        if gesture_signal.confirmed and gesture_signal.intent:
            # Feed into existing intent pipeline
            # NOTE: In full implementation, this would go through validator, confidence tracker, state machine
            # For now, we'll store it for potential processing
            self._process_gesture_intent(gesture_signal.intent)
    
    def _process_gesture_intent(self, intent: Intent):
        """
        Process a gesture-generated intent through the existing pipeline
        
        This is where gesture CONFIRM intents enter the same path
        as simulated CONFIRM intents
        
        NOTE: In full implementation, this would go through:
        - Validator
        - Confidence tracker
        - State machine
        - Router (still refuses execution in Week 4)
        """
        # For Week 4, we just log that intent was generated
        # Full intent processing pipeline would be implemented here
        logger.info(f"SystemOrchestrator: Gesture intent generated: {intent.type.value} from {intent.source}")
        
        # In full implementation:
        # validated_intent = self.validator.validate(intent)
        # confidence_result = self.confidence_tracker.update(validated_intent)
        # self.state_machine.update(intent=validated_intent, ...)
        # Router would still refuse execution in Week 4
    
    def _multi_object_tick(self, timestamp: float):
        """
        Multi-object processing (NEW - Week 7)
        
        Pipeline:
        1. Get all tracked objects
        2. Detect oscillation
        3. Rank candidates (with suppression)
        4. Update scope signal with ranked primary
        """
        
        if not self.camera_scope_controller or not hasattr(self.camera_scope_controller, 'tracker'):
            return
        
        tracker = self.camera_scope_controller.tracker
        if not tracker:
            return
        
        # Get all confirmed tracked objects
        all_tracks = tracker.get_all_tracks()
        tracked_objects = [
            TrackedObject.from_track(track)
            for track in all_tracks
            if track.confirmed  # Only confirmed tracks
        ]
        
        # Get current primary ID (for oscillation detection)
        current_primary_id = (self.last_scope_signal.scoped_object_id 
                             if self.last_scope_signal else None)
        
        # Detect oscillation
        oscillation_result = self.oscillation_detector.update(
            primary_id=current_primary_id,
            timestamp=timestamp
        )
        self.oscillation_result = oscillation_result
        
        # Log oscillation events
        if oscillation_result.oscillating:
            self.logger.log_event({
                "type": "oscillation_detected",
                "timestamp": timestamp,
                "suppressed_ids": oscillation_result.suppressed_ids,
                "suppressed_until": oscillation_result.suppressed_until,
                "reason": oscillation_result.reason,
                "switch_count": oscillation_result.switch_count
            })
        
        # Rank candidates (with suppression)
        frame_width = self.last_camera_frame.width if self.last_camera_frame else 640
        frame_height = self.last_camera_frame.height if self.last_camera_frame else 480
        frame_id = self.last_camera_frame.frame_id if self.last_camera_frame else self.tick_count
        
        ranked_candidates = self.candidate_ranker.rank(
            tracked_objects=tracked_objects,
            frame_width=frame_width,
            frame_height=frame_height,
            timestamp=timestamp,
            frame_id=frame_id,
            suppressed_ids=oscillation_result.suppressed_ids
        )
        self.ranked_candidates = ranked_candidates
        
        # Log ranking
        self.logger.log_event({
            "type": "candidate_ranked",
            "timestamp": timestamp,
            "primary_choice": (ranked_candidates.primary_choice.track_id 
                              if ranked_candidates.primary_choice else None),
            "primary_label": (ranked_candidates.primary_choice.label 
                             if ranked_candidates.primary_choice else None),
            "ambiguity_detected": ranked_candidates.ambiguity_detected,
            "margin": ranked_candidates.margin,
            "num_candidates": ranked_candidates.num_candidates,
            "reason": ranked_candidates.reason
        })
        
        # Note: Ranked primary feeds into existing scope stability logic
        # Camera scope controller will use this for focus commitment
    
    def _robustness_tick(self, timestamp: float):
        """
        Failure detection and recovery (ENHANCED Week 8)
        
        CRITICAL: Runs during vulnerable states
        Can trigger PAUSED state
        
        Checks:
        - Object loss (Week 7)
        - Hand loss (Week 7)
        - Ambiguity during confirmation (Week 7)
        - Confidence drop (NEW Week 8)
        - Attention timeout (NEW Week 8)
        - State uncertainty (NEW Week 8)
        
        Action:
        - Generate enhanced recovery plan
        - Trigger PAUSED if needed
        - Clear state as specified
        - Update state machine context
        """
        
        if not self.recovery_controller:
            return
        
        # Get current scoped object
        scoped_id = (self.last_scope_signal.scoped_object_id 
                    if self.last_scope_signal else None)
        
        # Get tracker
        tracker = None
        if self.camera_scope_controller and hasattr(self.camera_scope_controller, 'tracker'):
            tracker = self.camera_scope_controller.tracker
        
        # Get state estimate (Week 6)
        state_estimate = None
        if hasattr(self, 'affordance_engine') and self.affordance_engine:
            state_estimate = getattr(self.affordance_engine, 'last_state_estimate', None)
        
        # Get confidence history (if available)
        confidence_history = getattr(self, 'confidence_history', None)
        
        # Run comprehensive recovery check (ENHANCED Week 8)
        recovery_plan = self.recovery_controller.check(
            system_state=self.state_machine.current_state,
            scoped_object_id=scoped_id,
            ranked_candidates=self.ranked_candidates,
            hand_detection=self.last_hand_detection,
            tracker=tracker,
            state_estimate=state_estimate,
            confidence_history=confidence_history,
            timestamp=timestamp
        )
        
        self.last_recovery_plan = recovery_plan
        
        # Execute recovery plan if pause needed
        if recovery_plan.should_pause:
            self._execute_recovery_plan(recovery_plan, timestamp)
    
    def _execute_recovery_plan(self, plan: RecoveryPlan, timestamp: float):
        """
        Execute recovery plan (NEW Week 8)
        
        Actions:
        - Log pause trigger
        - Transition to PAUSED
        - Clear state as specified
        - Update state machine context
        - Set recovery flag
        """
        
        # Log pause trigger
        self.logger.log_event({
            "type": "pause_triggered",
            "timestamp": timestamp,
            "trigger": plan.trigger.value if plan.trigger else None,
            "reason": plan.reason,
            "system_state": plan.system_state_at_pause,
            "evidence": plan.evidence,
            "recovery_actions": [a.value for a in plan.recovery_actions]
        })
        
        # Transition to PAUSED via state machine
        self.state_machine.transition_to(SystemState.PAUSED)
        
        # Update state machine context (NEW Week 8)
        self.state_machine.context.pause_trigger = plan.trigger.value if plan.trigger else None
        self.state_machine.context.pause_reason = plan.reason
        self.state_machine.context.pause_timestamp = timestamp
        self.state_machine.context.recovery_required = True
        self.state_machine.context.recovery_instructions = [
            f"{action.value}: {plan.recovery_explanation}" 
            for action in plan.recovery_actions
        ]
        
        # Clear state as specified
        if plan.clear_scope:
            self.last_scope_signal = None
            # Clear camera scope controller stability
            if (self.camera_scope_controller and 
                hasattr(self.camera_scope_controller, 'stability_gate')):
                if hasattr(self.camera_scope_controller.stability_gate, 'reset'):
                    self.camera_scope_controller.stability_gate.reset()
        
        if plan.clear_confirmation:
            # Clear gesture confirmation
            if self.pinch_stability:
                self.pinch_stability.reset()
            if self.gesture_confirm_controller:
                if hasattr(self.gesture_confirm_controller, 'reset'):
                    self.gesture_confirm_controller.reset()
        
        if plan.clear_execution:
            # Clear execution state
            self.highlighted_option = None
            if hasattr(self.state_machine, 'execution_allowed'):
                self.state_machine.execution_allowed = False
            self.last_execution_result = None
        
        if plan.clear_undo:
            # Clear undo state (NEW Week 8)
            if self.undo_controller:
                self.undo_controller.cancel_undo("Cleared by pause")
        
        # Set recovery flag
        self.recovery_active = True
    
    def _option_highlighting_tick(self, timestamp: float):
        """
        Select highlighted option (Week 5)
        
        Week 5: Always first option
        Week 7+: Could cycle via gesture
        """
        if not self.current_affordances:
            self.highlighted_option = None
            return
        
        highlighted = self.option_selector.select(
            affordance_set=self.current_affordances,
            timestamp=timestamp
        )
        
        self.highlighted_option = highlighted
        
        if highlighted:
            self.logger.log_highlighted_option(highlighted)
    
    def _intent_tick(self, timestamp: float):
        """
        Process intents (MODIFIED for execution)
        
        Now includes:
        - Gesture-generated CONFIRM intents
        - Execution via Router
        - Action history recording
        """
        
        # Get current scope info
        current_scope_id = None
        current_scope_label = None
        current_scope_category = None
        
        if self.last_scope_signal and self.last_scope_signal.scoped_object_id:
            current_scope_id = self.last_scope_signal.scoped_object_id
            current_scope_label = self.last_scope_signal.object_label
            
            # Get category from affordances
            if self.current_affordances:
                current_scope_category = self.current_affordances.category.value
        
        # Detect scope change
        scope_changed = (current_scope_id != self.last_scope_id)
        if scope_changed:
            # Clear confirmation if scope changed
            if self.state_machine and self.state_machine.current_state in [SystemState.CONFIRMING, SystemState.UNDO_CONFIRMING]:
                self.state_machine.update(
                    intent=Intent(
                        type=IntentType.CANCEL,
                        confidence=1.0,
                        timestamp=timestamp,
                        source="system"
                    ),
                    timestamp=timestamp
                )
                self.logger.log_event({
                    "type": "confirmation_cleared",
                    "reason": "scope changed",
                    "timestamp": timestamp
                })
            
            self.last_scope_id = current_scope_id
        
        # Process gesture-generated CONFIRM intent
        if self.last_gesture_signal and self.last_gesture_signal.confirmed and self.last_gesture_signal.intent:
            intent = self.last_gesture_signal.intent
            if intent.type == IntentType.CONFIRM:
                # Update state machine
                if self.state_machine:
                    self.state_machine.update(
                        intent=intent,
                        scoped_object_id=current_scope_id,
                        timestamp=timestamp
                    )
        
        # === CHECK FOR EXECUTION (if state machine allows) ===
        if self.execution_enabled and self.state_machine and self.state_machine.execution_allowed:
            # Route to execution
            result = self.router.route(
                execution_allowed=True,
                highlighted_option=self.highlighted_option,
                scoped_object_id=current_scope_id,
                scoped_object_label=current_scope_label,
                scoped_category=current_scope_category,
                timestamp=timestamp
            )
            
            if result:
                # Log execution
                self.logger.log_execution_result(result)
                self.last_execution_result = result
                
                # Record in history if reversible
                if result.ok and result.reversible:
                    # Get action type from highlighted option
                    action_type_str = None
                    if self.highlighted_option:
                        action_type_str = self.highlighted_option.option.affordance_type.value
                    
                    record = ActionRecord.from_execution_result(
                        result=result,
                        object_id=current_scope_id or "",
                        object_label=current_scope_label or "",
                        category=current_scope_category or "",
                        action_type=action_type_str or "unknown",
                        undo_window_seconds=self.action_history.undo_window_seconds
                    )
                    self.action_history.record(record)
                    self.logger.log_action_recorded(record)
                
                # Clear execution flag (one action per confirmation)
                if self.state_machine:
                    self.state_machine.execution_allowed = False
                    self.state_machine.update(
                        intent=Intent(
                            type=IntentType.IDLE,
                            confidence=1.0,
                            timestamp=timestamp,
                            source="system"
                        ),
                        timestamp=timestamp
                    )
    
    def _undo_tick(self, timestamp: float):
        """
        Manage undo availability and state (ENHANCED Week 8)
        
        Responsibilities:
        - Check undo availability (state-aware)
        - Update state machine context
        - Handle keyboard 'U' trigger (Week 5 shortcut)
        - Manage UNDO_CONFIRMING state
        - Execute undo on confirmation
        """
        
        # Check if undo available (ENHANCED Week 8 - pass system_state)
        undo_available = self.undo_controller.is_undo_available(
            current_time=timestamp,
            system_state=self.state_machine.current_state if self.state_machine else None
        )
        
        # Update state machine context (NEW Week 8)
        if self.state_machine:
            self.state_machine.context.undo_available = undo_available
            
            if undo_available:
                undo_info = self.undo_controller.get_undo_info(timestamp)
                if undo_info:
                    self.state_machine.context.undo_expires_at = undo_info.get('time_remaining', 0) + timestamp
                    self.state_machine.context.undo_action_id = undo_info.get('action_id')
        
        # If in UNDO_CONFIRMING state, check for pinch confirmation
        if self.state_machine and self.state_machine.current_state == SystemState.UNDO_CONFIRMING:
            # Check if gesture confirmed
            if self.last_gesture_signal and self.last_gesture_signal.confirmed:
                # Execute undo (ENHANCED Week 8 - pass system_state)
                undo_result = self.undo_controller.confirm_undo(
                    current_time=timestamp,
                    system_state=self.state_machine.current_state
                )
                
                self.logger.log_undo_confirm(undo_result)
                
                # Transition back to IDLE
                self.state_machine.update(
                    intent=Intent(
                        type=IntentType.IDLE,
                        confidence=1.0,
                        timestamp=timestamp,
                        source="system"
                    ),
                    timestamp=timestamp
                )
                self.undo_controller.cancel_undo("Completed")
    
    def request_undo(self, timestamp: float):
        """
        Request undo (called from UI keyboard handler)
        
        ENHANCED Week 8: Validates system state
        Week 5: Triggered by 'U' key press
        """
        if not self.execution_enabled:
            return False, "Execution not enabled"
        
        # Request undo (ENHANCED Week 8 - pass system_state)
        success, reason = self.undo_controller.request_undo(
            current_time=timestamp,
            system_state=self.state_machine.current_state if self.state_machine else SystemState.IDLE
        )
        
        self.logger.log_undo_request(success, reason, timestamp)
        
        if success:
            # Transition to UNDO_CONFIRMING
            if self.state_machine:
                self.state_machine.update(
                    intent=Intent(
                        type=IntentType.UNDO_REQUEST,
                        confidence=1.0,
                        timestamp=timestamp,
                        source="keyboard"
                    ),
                    timestamp=timestamp
                )
        
        return success, reason
    
    def _apply_camera_scope_to_system(self, signal):
        """
        Apply camera scope signal to core state machine
        
        CRITICAL: Camera suggests, core system decides
        - Camera scope ≠ execution permission
        - Core safety gates still apply
        - This is a READ-ONLY suggestion
        """
        
        # If camera suggests PAUSED due to ambiguity
        if signal.ambiguity_detected:
            # Core system SHOULD pause, but decision is internal
            # We just provide the signal - state machine handles it
            # For now, we can optionally influence state (but core decides)
            if signal.suggested_state == SystemState.PAUSED:
                # Log ambiguity
                self.logger.log_ambiguity_detected(
                    frame_id=signal.frame_id,
                    timestamp=signal.timestamp,
                    reason=signal.focus_reason
                )
        
        # If camera suggests SCOPED
        if signal.suggested_state == SystemState.SCOPED:
            # Core system MAY scope if all safety checks pass
            # We don't force it - this is just a suggestion
            # The actual state machine logic would check this signal
            # For demo purposes, we can optionally update current_scope
            if signal.scoped_object_id:
                self.current_scope = signal.scoped_object_id
        
        # Camera signal is now available to:
        # - State machine (can check signal.suggested_state)
        # - Validator (can verify object validity)
        # - UI (can display current scope)
        
        # But camera NEVER bypasses:
        # - Identity gate
        # - Confidence tracker
        # - Ambiguity detector
        # - Safety sandbox
    
    def _string_to_system_state(self, state_str: str) -> SystemState:
        """Convert string state to SystemState enum."""
        state_map = {
            "IDLE": SystemState.IDLE,
            "SCOPED": SystemState.SCOPED,
            "CONFIRMING": SystemState.CONFIRMING,
            "EXECUTING": SystemState.EXECUTING,
            "PAUSED": SystemState.PAUSED,
            "UNDO_CONFIRMING": SystemState.UNDO_CONFIRMING
        }
        return state_map.get(state_str, SystemState.IDLE)
    
    def _get_block_reason(self) -> Optional[str]:
        """Get reason why execution is blocked."""
        if self.current_state == "IDLE":
            return "No scope selected"
        elif self.current_state == "SCOPED":
            return "Waiting for confirmation"
        elif self.current_state == "CONFIRMING":
            return "Waiting for stable confidence"
        elif self.current_state == "PAUSED":
            return "System paused: identity uncertainty"
        return None
    
    def get_ui_snapshot(self, timestamp: float) -> Dict:
        """
        Get complete UI snapshot for visualization.
        
        This aggregates all system state for display.
        """
        
        # Simulate authority gates based on state
        gates = {
            "scope_present": self.current_state in ["SCOPED", "CONFIRMING", "EXECUTING"],
            "confirmation_received": self.current_state in ["CONFIRMING", "EXECUTING"],
            "ambiguity_detected": random.random() < 0.1,  # 10% chance
            "identity_valid": self.current_state != "PAUSED",
            "lock_acquired": self.current_state == "EXECUTING",
            "confidence_stable": random.random() > 0.3,  # 70% chance
            "execution_allowed": self.current_state == "EXECUTING"
        }
        
        # Get system state from state machine if available
        system_state_str = self.current_state
        if self.state_machine:
            system_state_str = self.state_machine.current_state.value
        
        ui_snapshot = {
            "timestamp": timestamp,
            "system_status": system_state_str,
            "system_state": system_state_str,  # For compatibility
            "current_user": self.current_user,
            "why_nothing_happened": self._get_block_reason(),
            
            # Timeline (last 5 events)
            "recent_timeline": self.timeline_events[-5:] if self.timeline_events else [],
            
            # Authority gates
            "authority_gates": gates,
            
            # Multi-object context
            "multi_object_context": {
                "active_candidates": random.randint(1, 3),
                "primary_focus": self.current_scope or random.choice(["obj_left", "obj_center", "obj_right", None]),
                "ambiguity_detected": gates["ambiguity_detected"],
                "shift_event": None
            },
            
            # Multi-user state
            "user_states": {
                "user_A": {
                    "state": system_state_str,
                    "scope": self.current_scope,
                    "can_undo": random.random() > 0.7
                },
                "user_B": {
                    "state": "IDLE",
                    "scope": None,
                    "can_undo": False
                }
            },
            
            # World state (use real world if execution enabled, otherwise simulated)
            "world_objects": self.world.get_all_objects() if self.execution_enabled else {
                "obj_left": {
                    "state": {"toggled": random.random() > 0.5},
                    "owner": None,
                    "locked_by": None
                },
                "obj_center": {
                    "state": {"toggled": random.random() > 0.5},
                    "owner": None,
                    "locked_by": "user_B" if random.random() > 0.8 else None
                },
                "obj_right": {
                    "state": {"toggled": random.random() > 0.5},
                    "owner": None,
                    "locked_by": None
                }
            },
            
            # Prediction/Proposal (sometimes present)
            "prediction": {
                "predicted_type": "CONFIRM",
                "probability": 0.72,
                "target_id": "obj_left"
            } if random.random() > 0.6 else None,
            
            "proposal": {
                "type": "PROPOSE_TOGGLE",
                "target_id": "obj_left"
            } if random.random() > 0.7 else None,
            
            # Recovery/Undo
            "paused_users": ["user_A"] if system_state_str == "PAUSED" else [],
            "pause_reason": "Identity uncertainty" if system_state_str == "PAUSED" else None,
            "undo_available": {
                "user_A": random.random() > 0.8
            },
            "undo_time_remaining": {
                "user_A": random.uniform(3.0, 8.0)
            } if random.random() > 0.8 else {}
        }
        
        # Add scope info (Week 2)
        if self.last_scope_signal:
            ui_snapshot['scope'] = {
                'object_id': self.last_scope_signal.scoped_object_id,
                'object_label': self.last_scope_signal.object_label,
                'confidence': self.last_scope_signal.confidence,
                'ambiguity': self.last_scope_signal.ambiguity_detected
            }
        
        # Add affordances (Week 3)
        if self.current_affordances:
            ui_snapshot['affordances'] = {
                'category': self.current_affordances.category.value,
                'category_confidence': self.current_affordances.category_confidence,
                'options': [
                    {
                        'title': opt.title,
                        'description': opt.description,
                        'risk': opt.risk.value,
                        'confidence': opt.confidence,
                        'affordance_type': opt.affordance_type.value
                    }
                    for opt in self.current_affordances.options
                ],
                'blocked': self.current_affordances.blocked,
                'block_reason': self.current_affordances.block_reason
            }
        
        # Add highlighted option (Week 5)
        if self.highlighted_option:
            ui_snapshot['highlighted_option'] = {
                'index': self.highlighted_option.option_index,
                'title': self.highlighted_option.option.title,
                'risk': self.highlighted_option.option.risk.value,
                'reason': self.highlighted_option.reason,
                'affordance_type': self.highlighted_option.option.affordance_type.value
            }
        
        # Add execution result (Week 5)
        if self.last_execution_result:
            ui_snapshot['last_execution'] = {
                'ok': self.last_execution_result.ok,
                'reason': self.last_execution_result.reason,
                'before_state': self.last_execution_result.before_state,
                'after_state': self.last_execution_result.after_state,
                'reversible': self.last_execution_result.reversible,
                'action_id': self.last_execution_result.action_id
            }
        
        # Add undo info (Week 5)
        if self.execution_enabled:
            undo_info = self.undo_controller.get_undo_info(timestamp)
            ui_snapshot['undo_info'] = undo_info
        
        # Add camera visualization (if available)
        if self.camera_enabled and self.last_camera_frame is not None:
            try:
                # Get state from state machine if available
                if self.state_machine:
                    system_state_enum = self.state_machine.current_state
                else:
                    # Convert string state to SystemState enum for overlay
                    system_state_enum = self._string_to_system_state(self.current_state)
                
                # Prepare gesture data for overlay
                gesture_overlay_data = None
                if self.gesture_enabled and self.last_pinch_state:
                    gesture_overlay_data = {
                        'pinching': self.last_pinch_state.stable,
                        'frames_held': self.last_pinch_state.frames_held,
                        'confirmed': self.last_pinch_state.confirmed,
                        'blocked': self.last_gesture_signal.blocked if self.last_gesture_signal else False,
                        'block_reason': self.last_gesture_signal.block_reason if self.last_gesture_signal else ""
                    }
                
                annotated_frame = self.camera_overlay.render(
                    frame=self.last_camera_frame.image,
                    scope_signal=self.last_scope_signal,
                    detection_result=self.last_detection_result,
                    tracking_result=self.last_tracking_result,
                    system_state=system_state_enum,
                    gesture_data=gesture_overlay_data
                )
                ui_snapshot['camera_frame'] = annotated_frame
            except Exception as e:
                logger.error(f"SystemOrchestrator: Failed to render camera overlay: {e}")
        
        # Add affordance info to snapshot (NEW - Week 3)
        if self.current_affordances:
            ui_snapshot['affordances'] = {
                'category': self.current_affordances.category.value,
                'category_confidence': self.current_affordances.category_confidence,
                'options': [
                    {
                        'title': opt.title,
                        'description': opt.description,
                        'affordance_type': opt.affordance_type.value,
                        'risk': opt.risk.value,
                        'confidence': opt.confidence,
                        'reason': opt.reason
                    }
                    for opt in self.current_affordances.options
                ],
                'blocked': self.current_affordances.blocked,
                'block_reason': self.current_affordances.block_reason,
                'object_id': self.current_affordances.object_id,
                'object_label': self.current_affordances.object_label
            }
        
        # Add multi-object info (NEW - Week 7)
        if self.multi_object_enabled:
            if self.ranked_candidates:
                ui_snapshot['multi_object'] = {
                    'num_candidates': self.ranked_candidates.num_candidates,
                    'primary_id': (self.ranked_candidates.primary_choice.track_id 
                                  if self.ranked_candidates.primary_choice else None),
                    'primary_label': (self.ranked_candidates.primary_choice.label 
                                     if self.ranked_candidates.primary_choice else None),
                    'ambiguity_detected': self.ranked_candidates.ambiguity_detected,
                    'margin': self.ranked_candidates.margin,
                    'is_clear_choice': self.ranked_candidates.is_clear_choice,
                    'reason': self.ranked_candidates.reason,
                    'candidates': [
                        {
                            'track_id': c.tracked_object.track_id,
                            'label': c.tracked_object.label,
                            'total_score': c.total_score,
                            'rank': c.rank
                        }
                        for c in self.ranked_candidates.candidates[:5]  # Top 5 only
                    ]
                }
            
            if self.oscillation_result:
                ui_snapshot['oscillation'] = {
                    'oscillating': self.oscillation_result.oscillating,
                    'suppressed_ids': self.oscillation_result.suppressed_ids,
                    'suppressed_until': self.oscillation_result.suppressed_until,
                    'reason': self.oscillation_result.reason,
                    'switch_count': self.oscillation_result.switch_count
                }
        
        # Add recovery info (ENHANCED Week 8)
        if self.last_recovery_plan and self.last_recovery_plan.should_pause:
            ui_snapshot['recovery'] = {
                'paused': True,
                'trigger': self.last_recovery_plan.trigger.value if self.last_recovery_plan.trigger else None,
                'reason': self.last_recovery_plan.reason,
                'recovery_actions': [a.value for a in self.last_recovery_plan.recovery_actions],
                'recovery_explanation': self.last_recovery_plan.recovery_explanation,
                'evidence': self.last_recovery_plan.evidence,
                'timestamp': self.last_recovery_plan.timestamp
            }
        
        # State machine context (NEW Week 8)
        if self.state_machine and hasattr(self.state_machine, 'context'):
            ui_snapshot['context'] = {
                'pause_trigger': self.state_machine.context.pause_trigger,
                'pause_reason': self.state_machine.context.pause_reason,
                'pause_timestamp': self.state_machine.context.pause_timestamp,
                'recovery_required': self.state_machine.context.recovery_required,
                'recovery_steps_completed': self.state_machine.context.recovery_steps_completed,
                'recovery_instructions': self.state_machine.context.recovery_instructions,
                'undo_available': self.state_machine.context.undo_available,
                'undo_expires_at': self.state_machine.context.undo_expires_at,
                'undo_action_id': self.state_machine.context.undo_action_id
            }
        
        return ui_snapshot
    
    def _evaluate_authority_gates(self, timestamp: float) -> tuple[Dict[str, bool], Dict[str, str]]:
        """
        Evaluate all authority gates (NEW Week 9)
        
        Returns tuple of (gates_status, gate_reasons)
        
        Gates checked (in order of importance):
        1. scope_present - Is there a scoped object?
        2. scope_stable - Has scope been stable long enough?
        3. no_ambiguity - Are we certain about which object?
        4. affordances_available - Are actions available?
        5. confirmation_valid - Is confirmation complete?
        6. not_paused - Is system active (not paused)?
        7. execution_allowed - Final execution permission
        """
        gates = {}
        reasons = {}
        
        # Gate 1: Scope Present
        has_scope = (self.last_scope_signal is not None and 
                    self.last_scope_signal.scoped_object_id is not None)
        gates['scope_present'] = has_scope
        if not has_scope:
            reasons['scope_present'] = "No object currently scoped"
        
        # Gate 2: Scope Stable
        scope_stable = False
        if has_scope and self.last_scope_signal:
            scope_stable = (self.last_scope_signal.confidence >= 
                          self.config.get('camera_scope', {}).get('min_scope_confidence', 0.6))
        gates['scope_stable'] = scope_stable
        if not scope_stable and has_scope:
            reasons['scope_stable'] = "Scope confidence too low or unstable"
        
        # Gate 3: No Ambiguity
        no_ambiguity = True
        if self.ranked_candidates and self.ranked_candidates.ambiguity_detected:
            no_ambiguity = False
            reasons['no_ambiguity'] = self.ranked_candidates.reason
        gates['no_ambiguity'] = no_ambiguity
        
        # Gate 4: Affordances Available
        affordances_ok = (self.current_affordances is not None and
                         len(self.current_affordances.options) > 0)
        gates['affordances_available'] = affordances_ok
        if not affordances_ok:
            reasons['affordances_available'] = "No actions available for current object"
        
        # Gate 5: Confirmation Valid
        confirmation_ok = False
        if self.last_gesture_signal and not self.last_gesture_signal.blocked:
            confirmation_ok = self.last_gesture_signal.confirmed
        gates['confirmation_valid'] = confirmation_ok
        if not confirmation_ok:
            if self.last_gesture_signal and self.last_gesture_signal.blocked:
                reasons['confirmation_valid'] = self.last_gesture_signal.block_reason
            else:
                reasons['confirmation_valid'] = "Gesture confirmation not complete"
        
        # Gate 6: Not Paused
        not_paused = True
        if self.state_machine:
            not_paused = (self.state_machine.current_state != SystemState.PAUSED and
                         self.state_machine.current_state != SystemState.RECOVERING)
        gates['not_paused'] = not_paused
        if not not_paused:
            pause_reason = "System paused"
            if self.state_machine and hasattr(self.state_machine, 'context'):
                pause_reason = self.state_machine.context.pause_reason or "System paused"
            reasons['not_paused'] = pause_reason
        
        # Gate 7: Execution Allowed (final check)
        execution_allowed = all([
            gates.get('scope_present', False),
            gates.get('scope_stable', False),
            gates.get('no_ambiguity', False),
            gates.get('affordances_available', False),
            gates.get('confirmation_valid', False),
            gates.get('not_paused', False)
        ])
        gates['execution_allowed'] = execution_allowed
        if not execution_allowed:
            # Find first blocking gate
            blocking = [name for name, passed in gates.items() if not passed and name != 'execution_allowed']
            if blocking:
                reasons['execution_allowed'] = f"Blocked by: {', '.join(blocking)}"
            else:
                reasons['execution_allowed'] = "Execution not permitted"
        
        return gates, reasons
    
    def _build_ui_snapshot(self, timestamp: float) -> UISnapshot:
        """
        Build complete UI snapshot (NEW Week 9)
        
        Replaces get_ui_snapshot() with strongly-typed UISnapshot.
        Extracts all information from subsystems into pure data structure.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            Complete UISnapshot for this frame
        """
        self.frame_id_counter += 1
        system_time_ms = (timestamp - self.session_start_time) * 1000
        
        # Evaluate authority gates
        authority_gates, authority_gate_reasons = self._evaluate_authority_gates(timestamp)
        
        # Get system state
        system_state = self.state_machine.current_state.value if self.state_machine else 'idle'
        system_state_reason = ""
        
        if self.state_machine and hasattr(self.state_machine, 'context'):
            if self.state_machine.context.pause_reason:
                system_state_reason = self.state_machine.context.pause_reason
            elif system_state == 'scoped' and self.last_scope_signal:
                system_state_reason = f"Object scoped: {self.last_scope_signal.object_label}"
            elif system_state == 'confirming':
                system_state_reason = "Awaiting gesture confirmation"
            elif system_state == 'executing':
                system_state_reason = "Executing action"
        
        # Scope info
        scope_status = 'none'
        scoped_object_id = None
        scoped_object_label = None
        scoped_object_category = None
        scope_confidence = 0.0
        scope_stable_frames = 0
        
        if self.last_scope_signal and self.last_scope_signal.scoped_object_id:
            scope_status = 'stable'
            scoped_object_id = self.last_scope_signal.scoped_object_id
            scoped_object_label = self.last_scope_signal.object_label
            
            # Get category from different sources (object_category may not exist)
            if hasattr(self.last_scope_signal, 'object_category'):
                scoped_object_category = self.last_scope_signal.object_category
            elif hasattr(self.last_scope_signal, 'category'):
                scoped_object_category = self.last_scope_signal.category
            elif self.current_affordances:
                scoped_object_category = self.current_affordances.category.value if hasattr(self.current_affordances.category, 'value') else str(self.current_affordances.category)
            else:
                scoped_object_category = None
            
            scope_confidence = self.last_scope_signal.confidence
            # TODO: Get stable_frames from scope controller
        
        # Multi-object scene
        num_tracked_objects = 0
        primary_object_id = None
        ambiguity_detected = False
        ambiguity_reason = ""
        oscillation_detected = False
        oscillation_reason = ""
        suppressed_object_ids = []
        
        if self.ranked_candidates:
            num_tracked_objects = self.ranked_candidates.num_candidates
            if self.ranked_candidates.primary_choice:
                primary_object_id = self.ranked_candidates.primary_choice.track_id
            ambiguity_detected = self.ranked_candidates.ambiguity_detected
            ambiguity_reason = self.ranked_candidates.reason
        
        if self.oscillation_result:
            oscillation_detected = self.oscillation_result.oscillating
            oscillation_reason = self.oscillation_result.reason
            suppressed_object_ids = self.oscillation_result.suppressed_ids
        
        # State inference
        state_estimate = None
        state_confidence = 0.0
        state_method = ""
        state_reasoning = ""

        # Get state estimate from affordance engine if available
        last_state_estimate = None
        if hasattr(self, 'affordance_engine') and self.affordance_engine:
            last_state_estimate = getattr(self.affordance_engine, 'last_state_estimate', None)
        
        if last_state_estimate:
            state_estimate = {'state': last_state_estimate.state}
            state_confidence = last_state_estimate.confidence
            state_method = last_state_estimate.method
            state_reasoning = last_state_estimate.reason
        
        # Affordances
        affordances_available = False
        affordances_blocked = False
        affordances_block_reason = ""
        affordance_options = []
        highlighted_option_index = None
        
        if self.current_affordances:
            affordances_available = len(self.current_affordances.options) > 0
            affordance_options = [
                {
                    'type': opt.action_type.value if hasattr(opt.action_type, 'value') else str(opt.action_type),
                    'title': opt.title,
                    'confidence': opt.confidence,
                    'requires_confirmation': opt.requires_confirmation
                }
                for opt in self.current_affordances.options
            ]
        
        if self.highlighted_option:
            highlighted_option_index = self.highlighted_option.index
        
        # Gesture/Confirmation
        hand_detected = False
        hand_confidence = 0.0
        pinch_detected = False
        pinch_stable_frames = 0
        pinch_required_frames = 6
        confirmation_state = 'none'
        
        if self.last_hand_detection:
            hand_detected = self.last_hand_detection.detected
            hand_confidence = self.last_hand_detection.confidence
        
        if self.last_pinch_state:
            pinch_detected = self.last_pinch_state.stable
            pinch_stable_frames = self.last_pinch_state.frames_held
            pinch_required_frames = self.config.get('pinch_stability', {}).get('min_stable_frames', 6)
            
            if self.last_pinch_state.confirmed:
                confirmation_state = 'confirmed'
            elif self.last_pinch_state.stable:
                confirmation_state = 'confirming'
        
        # Execution
        execution_result = None
        last_action_type = None
        last_action_timestamp = None
        
        if self.last_execution_result:
            execution_result = {
                'ok': self.last_execution_result.ok,
                'reason': self.last_execution_result.reason
            }
            last_action_type = self.last_execution_result.action_type
            last_action_timestamp = self.last_execution_result.timestamp
        
        # Undo
        undo_available = False
        undo_action_type = None
        undo_object_label = None
        undo_time_remaining = None
        undo_confirming = False
        
        if self.state_machine and hasattr(self.state_machine, 'context'):
            undo_available = self.state_machine.context.undo_available
            if undo_available and self.state_machine.context.undo_expires_at:
                undo_time_remaining = self.state_machine.context.undo_expires_at - timestamp
            undo_confirming = (self.state_machine.current_state == SystemState.UNDO_CONFIRMING)
            
            # Get undo details from history
            if undo_available and self.action_history:
                last_action = self.action_history.get_last_action()
                if last_action:
                    undo_action_type = last_action.action_type
                    undo_object_label = last_action.object_label
        
        # Recovery
        paused = (system_state == 'paused')
        pause_trigger = None
        pause_reason = ""
        recovery_required = False
        recovery_steps = []
        recovery_explanation = ""
        
        if self.last_recovery_plan and self.last_recovery_plan.should_pause:
            paused = True
            pause_trigger = self.last_recovery_plan.trigger.value if self.last_recovery_plan.trigger else None
            pause_reason = self.last_recovery_plan.reason
            recovery_required = True
            recovery_steps = [a.value for a in self.last_recovery_plan.recovery_actions]
            recovery_explanation = self.last_recovery_plan.recovery_explanation
        
        # Narrative events
        recent_events = [
            {
                'timestamp': e.timestamp,
                'type': e.event_type.value if hasattr(e.event_type, 'value') else str(e.event_type),
                'narrative': e.narrative,
                'icon': e.icon,
                'severity': e.severity,
                'details': e.details
            }
            for e in self.narrative_logger.get_recent_events()
        ]
        
        current_narrative = self.narrative_logger.get_current_narrative()
        
        # Metrics
        session_metrics = self.metrics_collector.get_session_metrics().to_dict()
        safety_metrics = self.metrics_collector.get_safety_metrics()
        
        # Build UISnapshot
        snapshot = UISnapshot(
            timestamp=timestamp,
            frame_id=self.frame_id_counter,
            system_time_ms=system_time_ms,
            
            system_state=system_state,
            system_state_reason=system_state_reason,
            execution_allowed=authority_gates.get('execution_allowed', False),
            
            scope_status=scope_status,
            scoped_object_id=scoped_object_id,
            scoped_object_label=scoped_object_label,
            scoped_object_category=scoped_object_category,
            scope_confidence=scope_confidence,
            scope_stable_frames=scope_stable_frames,
            
            num_tracked_objects=num_tracked_objects,
            primary_object_id=primary_object_id,
            ambiguity_detected=ambiguity_detected,
            ambiguity_reason=ambiguity_reason,
            oscillation_detected=oscillation_detected,
            oscillation_reason=oscillation_reason,
            suppressed_object_ids=suppressed_object_ids,
            
            state_estimate=state_estimate,
            state_confidence=state_confidence,
            state_method=state_method,
            state_reasoning=state_reasoning,
            
            affordances_available=affordances_available,
            affordances_blocked=affordances_blocked,
            affordances_block_reason=affordances_block_reason,
            affordance_options=affordance_options,
            highlighted_option_index=highlighted_option_index,
            
            hand_detected=hand_detected,
            hand_confidence=hand_confidence,
            pinch_detected=pinch_detected,
            pinch_stable_frames=pinch_stable_frames,
            pinch_required_frames=pinch_required_frames,
            confirmation_state=confirmation_state,
            
            authority_gates=authority_gates,
            authority_gate_reasons=authority_gate_reasons,
            
            execution_result=execution_result,
            last_action_type=last_action_type,
            last_action_timestamp=last_action_timestamp,
            
            undo_available=undo_available,
            undo_action_type=undo_action_type,
            undo_object_label=undo_object_label,
            undo_time_remaining=undo_time_remaining,
            undo_confirming=undo_confirming,
            
            paused=paused,
            pause_trigger=pause_trigger,
            pause_reason=pause_reason,
            recovery_required=recovery_required,
            recovery_steps=recovery_steps,
            recovery_explanation=recovery_explanation,
            
            recent_events=recent_events,
            current_narrative=current_narrative,
            
            session_metrics=session_metrics,
            safety_metrics=safety_metrics
        )
        
        # Record frame in metrics
        self.metrics_collector.record_frame(snapshot)
        
        return snapshot
    
    def cleanup(self):
        """Cleanup resources (camera stream, logger, etc.)."""
        if self.camera_enabled and hasattr(self, 'camera_stream'):
            try:
                self.camera_stream.stop()
                logger.info("SystemOrchestrator: Camera stream stopped")
            except Exception as e:
                logger.error(f"SystemOrchestrator: Error stopping camera: {e}")
        
        # Close video session logger (NEW - Week 7)
        if hasattr(self, 'video_logger') and self.video_logger:
            try:
                stats = self.video_logger.get_statistics()
                self.video_logger.close()
                logger.info(f"SystemOrchestrator: Video session logger closed "
                          f"(logged {stats['snapshots_logged']}/{stats['frame_count']} frames, "
                          f"compression={stats['compression_ratio']:.2%})")
            except Exception as e:
                logger.error(f"SystemOrchestrator: Error closing video logger: {e}")
        
        if hasattr(self, 'logger'):
            try:
                self.logger.close()
                logger.info("SystemOrchestrator: Event logger closed")
            except Exception as e:
                logger.error(f"SystemOrchestrator: Error closing logger: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()

