"""
Arm orchestrator - central integration point for control loop.
Week 4: Integrates state machine + input + world model.
Week 5: Integrates controller for autonomous execution.
Week 8: Integrates recovery controller for safety.
Week 9: Integrates logging, metrics, and narrative.
"""

from typing import Dict, Any, TYPE_CHECKING, Optional
import time
from pathlib import Path
import pybullet as p
from .arm_state_machine import ArmStateMachine
from .arm_intent_schema import ArmUIState, DecisionSignal, ArmDecision
from robotics import ArmController, SafetyMonitor, ArmRecoveryController
from robotics.execution_result import ExecutionResult
from robotics.arm_simulator import is_valid_body
from utils.safe_pybullet import safe_get_pose
from .arm_trust_metrics import ArmTrustMetrics
from .arm_ui_snapshot import ArmUISnapshot
from .arm_event_logger import ArmEventLogger, EventType
from .arm_narrative_logger import ArmNarrativeLogger
from .arm_metrics_collector import ArmMetricsCollector
from sim import FaultInjector, FaultType

if TYPE_CHECKING:
    from input import EEGDecisionSource


class ArmOrchestrator:
    """
    Central orchestrator for arm control workflow.
    
    Responsibilities:
    - Own state machine
    - Read user input (keyboard/EEG)
    - Update world model
    - Advance state machine
    - Manage controller (Week 5)
    - Generate UI snapshots
    
    Paper concept: "Integrator" that connects all subsystems.
    """
    
    def __init__(self, cfg: dict, use_eeg: bool = False, eeg_source: str = "mock", 
                 fault_injector: Optional[FaultInjector] = None, session_id: Optional[str] = None):
        """
        Initialize orchestrator.
        
        Args:
            cfg: Configuration dict
            use_eeg: If True, use EEG (BrainLink or Mock)
            eeg_source: "brainlink" or "mock"
            fault_injector: Optional fault injector for testing
            session_id: Optional session ID (auto-generated if None)
        """
        self.cfg = cfg
        self.state_machine = ArmStateMachine()
        self.controller = ArmController(cfg)
        
        # Week 8: Safety and recovery
        self.safety_monitor = SafetyMonitor(cfg)
        self.recovery_controller = ArmRecoveryController(cfg)
        self.trust_metrics = ArmTrustMetrics()
        self.fault_injector = fault_injector
        
        # Week 9: Logging and metrics
        demo_cfg = cfg.get('demo', {})
        log_dir = demo_cfg.get('log_dir', 'logs')
        
        if session_id is None:
            from datetime import datetime
            fmt = demo_cfg.get('session_id_format', 'arm_%Y%m%d_%H%M%S')
            session_id = datetime.now().strftime(fmt)
        
        self.session_id = session_id
        
        # Event logger
        if demo_cfg.get('log_events', True):
            self.event_logger = ArmEventLogger(log_dir, session_id)
            self.event_logger.emit(EventType.SESSION_STARTED, {"session_id": session_id})
        else:
            self.event_logger = None
        
        # Narrative logger
        if demo_cfg.get('print_narrative', True):
            self.narrative_logger = ArmNarrativeLogger(verbose=True)
        else:
            self.narrative_logger = None
        
        # Metrics collector
        self.metrics_collector = ArmMetricsCollector(self.trust_metrics)
        
        # Performance tracking
        self.frame_count = 0
        self.last_frame_time = time.time()
        
        # Week 7: Select decision source based on config
        # Import here to avoid circular import
        from input import EEGDecisionSource, MockEEG, KeyboardConfirmInput, BrainLinkDecisionSource
        
        if use_eeg:
            if eeg_source == "brainlink":
                # Real BrainLink
                self.decision_source: EEGDecisionSource = BrainLinkDecisionSource(cfg)
                if not self.decision_source.start():
                    print("⚠️  BrainLink failed to start, falling back to MockEEG")
                    self.decision_source = MockEEG(mode="keyboard")
                    self.decision_source.start()
            else:
                # Mock EEG
                self.decision_source: EEGDecisionSource = MockEEG(mode="keyboard")
                self.decision_source.start()
            
            print(f"✓ Orchestrator initialized with {self.decision_source.get_source_name()}")
        else:
            # Fallback: keyboard input (Week 5 style)
            self.input = KeyboardConfirmInput()
            self.decision_source = None
            print("✓ Orchestrator initialized (keyboard only)")
        
        # Capture rest pose after first reset
        self._rest_pose_captured = False
        
        # Deferred forced lock (applied after world state is valid)
        self._pending_forced_lock = None
        
        # STEP C1: Deferred self-heal queue
        self._unlock_requested = False
        self._unlock_reason = None
        self._unlock_body_id = None
    
    def force_lock_target(self, object_id: int, selector=None):
        """
        Queue a forced target lock (applied next update).
        
        Layer 2: Idempotent - safe to call multiple times for same object.
        This method defers the lock application until after world.update_from_sim()
        runs, ensuring object state exists and eliminating race conditions.
        
        Args:
            object_id: Object ID to lock as target
            selector: Optional TargetSelector to check current lock state
        """
        # Idempotency check: already pending for same object?
        if self._pending_forced_lock == object_id:
            print(f"[FORCE LOCK] Already pending for object {object_id}")
            return
        
        # Check if already locked to this object (if selector provided)
        if selector is not None:
            if selector.is_locked() and selector.get_locked_target() == object_id:
                print(f"[FORCE LOCK] Already locked to object {object_id}")
                return
        
        # Check state machine (if available)
        if (self.state_machine.target_locked and 
            self.state_machine.active_target_id == object_id):
            print(f"[FORCE LOCK] Already locked to object {object_id} (state machine)")
            return
        
        # Queue new forced lock (last press wins if different object)
        if self._pending_forced_lock is not None and self._pending_forced_lock != object_id:
            print(f"[FORCE LOCK] Overwriting pending lock {self._pending_forced_lock} → {object_id}")
        
        self._pending_forced_lock = object_id
        print(f"[FORCE LOCK] Queued target lock for object {object_id}")
    
    def has_pending_forced_lock(self) -> bool:
        """
        Check if a forced lock is pending.
        
        Returns:
            True if forced lock is queued, False otherwise
        """
        return self._pending_forced_lock is not None
    
    def step(self, sim, world, selector) -> ArmUISnapshot:
        """
        Advance control loop one frame.
        
        Frame boundary: Process deferred self-heal FIRST.
        
        Args:
            sim: ArmSimulator instance
            world: WorldModel instance
            selector: TargetSelector instance
            
        Returns:
            UI snapshot (complete system state)
        """
        
        # STEP C2: FRAME BOUNDARY - Process deferred self-heal FIRST
        if self._unlock_requested:
            self._unlock_globally(world, selector, self._unlock_reason, self._unlock_body_id)
            self._unlock_requested = False
            self._unlock_reason = None
            self._unlock_body_id = None
        
        # Capture rest pose on first call
        if not self._rest_pose_captured:
            self.controller.capture_rest_pose(sim)
            self._rest_pose_captured = True
        
        # Update world model from simulator FIRST (ensures object state exists)
        world.update_from_sim(sim)
        
        # Apply pending forced lock AFTER world state is valid
        if self._pending_forced_lock is not None:
            target_id = self._pending_forced_lock
            
            # STEP B3: Validate body still exists (using safe wrapper)
            pose = safe_get_pose(target_id)
            
            if pose is None:
                print(f"[FORCE LOCK] ❌ Body {target_id} no longer valid, clearing pending lock")
                self._pending_forced_lock = None
                # Don't apply lock to invalid body - continue to next section
            else:
                # Body valid - apply lock
                try:
                    world.set_target(target_id, locked=True)
                    self.state_machine.set_target(target_id, locked=True)
                    selector.force_lock(target_id)
                    self._pending_forced_lock = None
                    print(f"[FORCE LOCK] ✅ Applied forced lock to object {target_id}")
                except Exception as e:
                    print(f"[FORCE LOCK] ❌ Failed to apply lock: {e}")
                    self._pending_forced_lock = None
        
        # Get selected target from selector
        target_id = selector.get_locked_target()
        target_locked = selector.is_locked()
        
        # Week 8: Apply fault injection (if enabled)
        active_faults = set()
        if self.fault_injector:
            active_faults = self.fault_injector.update(time.time())
        
        # Week 8: Override with faults
        if FaultType.TARGET_LOSS in active_faults:
            target_id = None
            target_locked = False
        
        # Update world model target
        world.set_target(target_id, target_locked)
        
        # Update state machine target
        self.state_machine.set_target(target_id, target_locked)
        
        # Read user decision (from EEG or keyboard)
        if self.decision_source is not None:
            signal = self.decision_source.read_signal()
            decision = ArmDecision.from_keyboard(signal) if signal != DecisionSignal.IDLE else ArmDecision.idle()
            print(f"[DBG ORCH] Decision from decision_source: {decision}")
        else:
            # Fallback to keyboard input
            # FIX: Read keys here FIRST (before main loop reads them)
            decision = self.input.read()
            print(f"[DBG ORCH] Decision from keyboard input: {decision}")
            print(f"[DBG ORCH] Decision type: {type(decision)}")
            print(f"[DBG ORCH] Decision signal: {decision.signal if hasattr(decision, 'signal') else 'NO SIGNAL ATTR'}")
        
        # Check if decision gets overwritten anywhere
        print(f"[DBG ORCH] About to pass decision to state machine: {decision}")
        
        # Week 7: Check EEG stability
        eeg_meta = None
        if self.decision_source is not None and hasattr(self.decision_source, 'get_debug_status'):
            eeg_meta = self.decision_source.get_debug_status()
            
            # Week 8: Override with faults
            if FaultType.EEG_DROPOUT in active_faults or FaultType.HIGH_VARIANCE in active_faults:
                eeg_meta['stable'] = False
                eeg_meta['blocked'] = True
                if FaultType.EEG_DROPOUT in active_faults:
                    eeg_meta['reason'] = "EEG dropout (injected fault)"
                else:
                    eeg_meta['reason'] = "High variance (injected fault)"
        
        # Week 8: Safety monitoring
        recovery_status = self.recovery_controller.get_status()
        
        if not self.recovery_controller.paused:
            # Only check safety if not already paused
            recovery_plan = self.safety_monitor.check(
                world, 
                self.state_machine, 
                self.controller, 
                eeg_meta, 
                selector
            )
            
            if recovery_plan.should_pause:
                # Trigger pause
                self.recovery_controller.trigger_pause(recovery_plan)
                self.state_machine.trigger_pause(str(recovery_plan.trigger))
                self.trust_metrics.record_pause(str(recovery_plan.trigger))
                
                # Freeze controller if configured
                if self.cfg['recovery']['freeze_on_pause']:
                    self.controller.freeze_hold(sim)
        else:
            # In PAUSED - check if recovery ready
            recovery_ready = self.recovery_controller.check_recovery_ready(
                world, eeg_meta, selector
            )
            self.state_machine.check_recovery_ready(recovery_ready)
            
            # If state machine exits PAUSED, clear recovery
            if self.state_machine.state != ArmUIState.PAUSED:
                self.recovery_controller.clear_pause()
                self.controller.unfreeze()
                self.safety_monitor.reset()
        
        # Check EEG stability (for blocking confirmations)
        self.state_machine.check_eeg_stability(eeg_meta, recovery_status)
        
        # Week 8: Track blocked confirmations
        if (self.state_machine.state == ArmUIState.AWAITING_CONFIRM and 
            eeg_meta and eeg_meta.get('blocked', False)):
            # Don't increment every frame, just when decision attempted
            if decision.signal == DecisionSignal.CONFIRM:
                self.trust_metrics.record_blocked_unstable()
        
        # Handle cancellation during execution
        if (self.state_machine.state == ArmUIState.EXECUTING and 
            decision.signal == DecisionSignal.CANCEL):
            self.state_machine.cancel_execution(self.controller)
            self.trust_metrics.record_execution_cancelled()
            
            # Week 8: Undo path
            if self.cfg['recovery']['undo']['enable_return_to_rest']:
                self.controller.undo_last_action(world, sim)
                self.trust_metrics.record_undo()
        
        # Advance state machine
        prev_state = self.state_machine.state
        print(f"[DBG ORCH] Calling state_machine.tick() with:")
        print(f"  Current state: {prev_state}")
        print(f"  Decision: {decision}")
        print(f"  Decision signal: {decision.signal if hasattr(decision, 'signal') else 'NO SIGNAL ATTR'}")
        print(f"  Active proposal: {self.state_machine.active_proposal}")
        
        self.state_machine.tick(world, decision, self.controller)
        
        print(f"[DBG ORCH] After tick, new state: {self.state_machine.state}")
        
        # Handle execution state transitions
        if self.state_machine.state == ArmUIState.EXECUTING:
            # Just entered EXECUTING state?
            if not self.controller.is_active():
                # Week 8: Verify confirmation before starting
                confirmed = (prev_state == ArmUIState.AWAITING_CONFIRM and 
                           decision.signal == DecisionSignal.CONFIRM)
                
                self.trust_metrics.record_execution_start(confirmed)
                
                # Start execution
                try:
                    self.controller.start_action(
                        self.state_machine.executing_action,
                        world,
                        sim
                    )
                except ValueError as e:
                    # Action not executable
                    print(f"⚠️  Cannot execute: {e}")
                    result = ExecutionResult(
                        success=False,
                        reason=str(e),
                        steps_used=0,
                        final_error_pos=0.0
                    )
                    self.state_machine.finish_execution(result)
                    self.trust_metrics.record_execution_complete(False)
            else:
                # Continue execution
                done, result = self.controller.tick(world, sim)
                
                if done and result is not None:
                    # Execution complete
                    print(f"✓ Execution result: {result}")
                    self.state_machine.finish_execution(result)
                    self.controller.reset()
                    self.trust_metrics.record_execution_complete(result.success)
        
        # Week 6: Update world model with grasp state
        gripper_snapshot = self.controller.get_gripper_snapshot()
        world.set_grasp_state(gripper_snapshot)
        
        # Build UI snapshot
        snapshot = self._build_ui_snapshot(world, selector, eeg_meta, recovery_status, active_faults)
        
        # Week 9: Update metrics collector
        dt = time.time() - self.last_frame_time
        self.metrics_collector.update(snapshot, dt)
        
        # Week 9: Print narrative
        if self.narrative_logger:
            lines = self.narrative_logger.describe(snapshot)
            for line in lines:
                print(line)
        
        # Increment frame count
        self.frame_count += 1
        
        return snapshot
    
    def _build_ui_snapshot(self, world, selector, eeg_meta, recovery_status, active_faults) -> ArmUISnapshot:
        """
        Build complete UI snapshot.
        
        Args:
            world: WorldModel
            selector: TargetSelector
            eeg_meta: EEG debug status
            recovery_status: Recovery controller status
            active_faults: Active fault types
            
        Returns:
            ArmUISnapshot with complete system state
        """
        # Get current time
        now = time.time()
        
        # Compute FPS
        dt = now - self.last_frame_time
        fps = 1.0 / dt if dt > 0 else 0.0
        self.last_frame_time = now
        
        # Get selection state
        selection_state = selector.tracker.get_state()
        hover_progress = 0.0
        if hasattr(selection_state, 'hover_frames') and selection_state.current_hover_id:
            dwell_frames = self.cfg.get('selection', {}).get('dwell_frames', 15)
            hover_progress = min(selection_state.hover_frames / dwell_frames, 1.0)
        
        # Build snapshot
        snapshot = ArmUISnapshot(
            timestamp=now,
            
            # Core state
            state=self.state_machine.state.value,
            last_event=self.state_machine.last_event or "",
            cooldown_frames=self.state_machine.cooldown_frames,
            
            # Target selection
            cursor_source="gaze" if selector.using_gaze else "mouse",
            hover_object_id=selection_state.current_hover_id if hasattr(selection_state, 'current_hover_id') else None,
            locked_object_id=selector.get_locked_target(),
            selection_locked=selector.is_locked(),
            hover_progress=hover_progress,
            
            # Proposal
            available_actions=[str(a) for a in world.get_available_actions()],
            proposed_action=str(self.state_machine.active_proposal.action_type) if self.state_machine.active_proposal else None,
            proposal_reason=self.state_machine.active_proposal.reason if self.state_machine.active_proposal else None,
            proposal_object_id=self.state_machine.active_proposal.target_object_id if self.state_machine.active_proposal else None,
            
            # Decision / EEG
            decision_source=self.decision_source.get_source_name() if self.decision_source else "keyboard",
            eeg_signal="IDLE",  # Could be enhanced to track actual signal
            eeg_attention=eeg_meta.get('attention') if eeg_meta else None,
            eeg_meditation=eeg_meta.get('meditation') if eeg_meta else None,
            eeg_stable=eeg_meta.get('stable', True) if eeg_meta else True,
            eeg_blocked=eeg_meta.get('blocked', False) if eeg_meta else False,
            eeg_blocked_reason=eeg_meta.get('reason') if eeg_meta else None,
            eeg_confidence=eeg_meta.get('confidence') if eeg_meta else None,
            cooldown_remaining_s=eeg_meta.get('cooldown_remaining', 0.0) if eeg_meta else 0.0,
            
            # Execution
            executing_action=str(self.state_machine.executing_action) if self.state_machine.executing_action else None,
            execution_progress=self.controller.get_progress(),
            execution_steps=self.controller.steps_used,
            execution_phase=self.controller.grasp_phase if hasattr(self.controller, 'grasp_phase') else None,
            
            # Grasp
            holding_object_id=self.controller.grasp_logic.get_held_object_id(),
            gripper_state="closed" if self.controller.gripper_state.value == "closed" else "open",
            
            # World state (optional, for debugging)
            ee_pos=list(world.ee_pos) if hasattr(world, 'ee_pos') else [0, 0, 0],
            obj_pos=list(world.object_pos) if hasattr(world, 'object_pos') else [0, 0, 0],
            # PATCH 4: Joint angles (first 3 joints for diagnostic display)
            joint_angles=list(world.arm_state.q[:3]) if world.arm_state is not None and len(world.arm_state.q) >= 3 else [0.0, 0.0, 0.0],
            
            # Execution result
            last_execution_result=None,  # TODO: Could store last result
            
            # Recovery
            paused=recovery_status.get('paused', False),
            pause_trigger=recovery_status.get('trigger'),
            pause_explanation=recovery_status.get('explanation', ''),
            pause_duration=recovery_status.get('pause_duration', 0.0),
            recovery_steps=recovery_status.get('required_steps', []),
            
            # Faults
            active_faults=[str(f) for f in active_faults],
            fault_injector_enabled=self.fault_injector is not None and self.fault_injector.enabled,
            
            # Trust metrics (headline)
            false_executions=self.trust_metrics.false_executions,
            executions_started=self.trust_metrics.executions_started,
            executions_completed=self.trust_metrics.executions_completed,
            pauses_triggered=self.trust_metrics.pauses_triggered,
            executions_blocked_unstable=self.trust_metrics.executions_blocked_unstable,
            
            # Performance
            fps=fps,
            frame_count=self.frame_count,
        )
        
        return snapshot
    
    def request_global_unlock(self, reason: str, body_id: Optional[int] = None):
        """
        Request global unlock (deferred to frame boundary).
        
        STEP C1: This is called by UI/rendering when invalid body detected.
        Actual unlock happens in step() at controlled point.
        
        Args:
            reason: Reason for unlock (e.g., "render_invalid_body", "manual_unlock")
            body_id: Optional body ID that triggered the unlock request
        """
        if not self._unlock_requested:
            self._unlock_requested = True
            self._unlock_reason = reason
            self._unlock_body_id = body_id
            print(f"[ORCHESTRATOR] Global unlock requested: {reason} (body={body_id})")
    
    def _unlock_globally(self, world, selector, reason: str, body_id: Optional[int] = None):
        """
        Unlock target globally across ALL subsystems (atomic operation).
        
        STEP C3: This ensures state consistency - all subsystems cleared together.
        Called only at frame boundary (never mid-execution).
        
        Args:
            world: WorldModel instance
            selector: TargetSelector instance
            reason: Reason for unlock
            body_id: Optional body ID that triggered the unlock
        """
        print(f"[ORCHESTRATOR] Executing global unlock: {reason}")
        
        # Clear pending forced lock
        if self._pending_forced_lock is not None:
            print(f"[ORCHESTRATOR]   - Clearing pending forced lock: {self._pending_forced_lock}")
            self._pending_forced_lock = None
        
        # Clear selector forced lock
        if selector.is_locked():
            locked_id = selector.get_locked_target()
            print(f"[ORCHESTRATOR]   - Clearing selector lock: {locked_id}")
            selector.clear_forced_lock()
            selector.manual_unlock()
        
        # Clear world target
        if world.target_object_id is not None:
            print(f"[ORCHESTRATOR]   - Clearing world target: {world.target_object_id}")
            world.set_target(None, locked=False)
        
        # Clear state machine target
        if self.state_machine.target_locked:
            print(f"[ORCHESTRATOR]   - Clearing state machine target: {self.state_machine.active_target_id}")
            self.state_machine.set_target(None, locked=False)
        
        print(f"[ORCHESTRATOR] Global unlock complete")
    
    def unlock_target(self, world=None, selector=None) -> None:
        """
        Public API for manual unlock (e.g., U key).
        
        STEP C: Uses deferred self-heal mechanism for consistency.
        
        Args:
            world: Optional WorldModel instance to sync
            selector: Optional TargetSelector instance to sync
        """
        if world is not None and selector is not None:
            # Direct unlock if both provided (for immediate unlock)
            self._unlock_globally(world, selector, "manual_unlock", None)
        else:
            # Queue for deferred unlock (for consistency with self-healing)
            self.request_global_unlock("manual_unlock", None)
    
    def reset(self) -> None:
        """Reset orchestrator (state machine + controller + safety)."""
        self.state_machine.reset()
        self.controller.reset()
        self.controller.grasp_logic.reset()
        self.safety_monitor.reset()
        self.recovery_controller.clear_pause()
        print("✓ Orchestrator reset")
    
    def get_session_id(self) -> str:
        """Get session ID."""
        return self.session_id
    
    def end_session(self) -> None:
        """End session and save metrics."""
        demo_cfg = self.cfg.get('demo', {})
        
        # Close event logger
        if self.event_logger:
            self.event_logger.emit(EventType.SESSION_ENDED, {
                "session_id": self.session_id,
                "frame_count": self.frame_count,
            })
            self.event_logger.close()
        
        # Save metrics if configured
        if demo_cfg.get('save_metrics', True):
            log_dir = Path(demo_cfg.get('log_dir', 'logs'))
            
            if demo_cfg.get('export_json', True):
                metrics_path = log_dir / f"{self.session_id}_metrics.json"
                self.metrics_collector.save_json(metrics_path)
            
            # Print summary
            self.metrics_collector.print_summary()
    
    def close(self) -> None:
        """Clean up resources."""
        # Week 9: End session (save metrics)
        self.end_session()
        
        # Close decision source
        if self.decision_source is not None:
            self.decision_source.close()
        
        # Reset grasp
        self.controller.grasp_logic.reset()
        
        # Week 8: Print trust metrics
        print("\n")
        self.trust_metrics.print_summary()
