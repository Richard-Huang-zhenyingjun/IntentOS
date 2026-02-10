"""
Core orchestrator - depends ONLY on abstract interfaces.

No concrete proposer, compiler, or input source imported here.
All concrete types are injected via constructor (from system_factory.py).

Week 7 additions:
- AuthorizationManager: token-based execution authorization
- TrustEngine: deterministic trust from execution outcomes
- AutonomyPolicy: A1 (per-object) / A2 (per-session) modes
- Re-auth: safe pause + new confirm on trust drop
"""
import time
import logging
import numpy as np
from typing import Optional, Callable
from src.core.schema import ArmDecision, DecisionSignal, UISnapshot, ArmActionType, ArmProposal, ArmUIState
from src.robot.world_state import WorldState
from src.core.state_machine import StateMachine
from src.core.trust_metrics import TrustMetrics

# Week 3: Core imports ONLY from interfaces
from src.interfaces import (
    SceneSummary, IntentProposal, ActionType as InterfaceActionType,
    ProposerBase, PlanCompilerBase,
    ExecStatus, ErrorCode,
    WorldArtifacts,
    Primitive,
)
# Week 5: Decision pipeline
from src.input.types import DecisionFrame, DecisionIntent
from src.input.pipeline import DecisionPipeline
from src.intelligence.proposer_registry import ProposerRegistry
from src.intelligence.scene_summarizer import SceneSummarizer
from src.execution.primitive_executor import PrimitiveExecutor, ExecutorStatus
from src.robot.simulator import RobotSimulator
from src.robot.controller import RobotController
from src.robot.grasp import GraspController

# Week 7: Authorization, Trust, Autonomy, Safe Pause
from src.core.authorization import AuthorizationManager, AuthScope
from src.core.trust import TrustEngine
from src.core.autonomy import AutonomyPolicy, AutonomyLevel, AUTONOMY_TO_SCOPE, AUTONOMY_MAX_OBJECTS
from src.execution.safe_pause import SafePauseHelper
from src.core.events import EventEmitter, EventType

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Core orchestrator with dependency injection.
    
    Week 3 refactor: All external dependencies injected,
    no concrete types imported. Orchestrator doesn't know
    if proposer is heuristic, Gemini, or something else.
    """
    
    def __init__(
        self,
        config: dict,
        decision_pipeline: DecisionPipeline,  # Week 5: Use pipeline
        sim: RobotSimulator,
        proposer_registry: ProposerRegistry,
        compiler: PlanCompilerBase,
        executor: PrimitiveExecutor,
        world_builder: Callable[[RobotSimulator, dict], WorldArtifacts],
        events: Optional[EventEmitter] = None  # Week 7: Event emitter
    ):
        """
        Initialize orchestrator with injected dependencies.
        
        Week 3: Dependencies injected from outside (factory/main script).
        Orchestrator depends ONLY on interfaces, not concrete implementations.
        
        Week 7: Added authorization, trust, autonomy, and safe pause components.
        
        Note: RobotController and GraspController still created here for now.
        TODO: Inject these as well for full interface-only design.
        """
        self.config = config
        
        # Input (Week 5: pipeline)
        self.decision_pipeline = decision_pipeline
        
        # Robot (TODO: Inject these in Week 3+)
        self.sim = sim
        self.controller = RobotController(config, sim)
        self.grasp = GraspController(sim)
        
        # Week 3: Dependencies injected (not created here)
        self.proposer_registry = proposer_registry
        self.compiler = compiler
        self.executor = executor
        
        # Week 3: Scene summarizer (created here for now, TODO: inject in Week 3+)
        self.scene_summarizer = SceneSummarizer(config)
        
        # Week 3: Build world using injected builder function
        self.world_artifacts = world_builder(sim, config)
        
        # Week 7: Event emitter
        self.events = events
        
        # Core state
        self.state_machine = StateMachine()
        self.trust_metrics = TrustMetrics()
        
        # Week 7: Authorization
        self.auth_manager = AuthorizationManager()
        
        # Week 7: Trust
        self.trust_engine = TrustEngine(config)
        
        # Week 7: Autonomy
        self.autonomy_policy = AutonomyPolicy.from_config(config)
        
        # Week 7: Safe pause
        self.safe_pause_helper = SafePauseHelper(config)
        
        # Week 7: Re-auth state
        self._safe_pause_primitives: list = []
        self._safe_pause_active: bool = False
        self._awaiting_reauth: bool = False
        self._awaiting_object_confirm: bool = False  # A1 mode: between objects
        
        # Week 7: Track current execution plan for trust updates
        self._current_execution_plan: Optional[list] = None
        self._current_object_index: int = 0
        
        # Frame tracking
        self.global_frame_counter: int = 0
        self.start_time = time.time()
        
        # Current state (Week 3: using interface types)
        self.current_scene: Optional[SceneSummary] = None
        self.current_proposal: Optional[IntentProposal] = None
        
        # Emit autonomy level set event
        if self.events:
            self.events.emit(
                EventType.AUTONOMY_LEVEL_SET,
                frame=0,
                data={'level': self.autonomy_policy.level.value},
            )
        
        print("[ORCH] ✓ Orchestrator initialized (Week 7: auth + trust + autonomy)")
        print(f"[ORCH]   Decision pipeline: active")
        print(f"[ORCH]   Proposer registry: {proposer_registry.get_active_proposer_name()}")
        print(f"[ORCH]   Autonomy level: {self.autonomy_policy.level.value}")
        if self.world_artifacts:
            print(f"[ORCH]   World artifacts: {len(self.world_artifacts.object_ids)} objects")
    
    def step(self) -> UISnapshot:
        """
        Main control loop (modified for Week 1, Week 7).
        
        Week 0 order:
        1. sim.step()
        2. read_world_state()
        3. read_decision()
        4. update_state_machine()
        5. execute if EXECUTING
        
        Week 1 additions:
        - Compute scene summary
        - Get proposal from proposer
        - Compile plan on confirm
        - Execute primitives via executor
        
        Week 7 additions:
        - Authorization token checks
        - Trust updates after primitives
        - Re-auth triggers
        - Safe pause execution
        - A1 per-object confirm flow
        """
        # Increment frame counter
        self.global_frame_counter += 1
        
        # 1. Physics step
        self.sim.step()
        
        # 2. Read world state
        world = self._read_world_state()
        
        # 3. Compute scene summary (Week 3: using SceneSummarizer class)
        self.current_scene = self.scene_summarizer.summarize(
            world, 
            self.world_artifacts,
            timestamp_frame=self.global_frame_counter
        )
        
        # Week 4: Update registry with FSM state (enables execution-phase gating)
        self.proposer_registry.update_fsm_state(self.state_machine.state.value)
        
        # 4. Read decision from pipeline (Week 5)
        decision_frame = self.decision_pipeline.tick(self.global_frame_counter)
        
        # Convert DecisionFrame to ArmDecision for state machine compatibility
        # TODO: Refactor state machine to use DecisionFrame directly
        if decision_frame.is_confirm:
            signal = DecisionSignal.CONFIRM
        elif decision_frame.is_cancel:
            signal = DecisionSignal.CANCEL
        else:
            signal = DecisionSignal.IDLE
        
        decision = ArmDecision(
            signal=signal,
            confidence=decision_frame.quality,
            source=decision_frame.source_type.value,
            timestamp=time.time()
        )
        
        # 5. State-specific logic (Week 7: enhanced with auth/trust)
        state = self.state_machine.state.value
        
        if state == 'idle':
            if decision_frame.is_confirm:
                self.state_machine._transition_to(ArmUIState.SELECTING)
        
        elif state == 'selecting':
            self.current_proposal = self.proposer_registry.propose(self.current_scene)
            if self.current_proposal and self.current_proposal.action != InterfaceActionType.IDLE:
                # Convert IntentProposal to ArmProposal for state machine
                arm_action = ArmActionType(self.current_proposal.action.value)
                self.state_machine.propose_action(arm_action, self.current_proposal.description)
        
        elif state == 'confirming':
            if decision_frame.is_confirm:
                self._handle_confirm(decision_frame)
            elif decision_frame.is_cancel:
                self.state_machine.reset()
        
        elif state == 'executing':
            if self._safe_pause_active:
                self._execute_safe_pause(world)
            elif self._awaiting_object_confirm:
                self._handle_awaiting_object_confirm(decision_frame)
            else:
                self._execute_task_with_trust(world)
        
        # 8. State machine tick
        self.state_machine.tick()
        
        # 9. Return UI snapshot (enhanced with scene info)
        return self._create_snapshot(world)
    
    def _read_world_state(self) -> WorldState:
        """Read current world state from simulator."""
        return WorldState(
            arm=self.sim.get_arm_state(),
            object=self.sim.get_object_state(),
            target_id=self.state_machine.target_id,
            holding=self.grasp.is_holding(),
            attached_id=self.grasp.get_attached_id()
        )
    
    def _update_state_machine(self, decision: ArmDecision, proposal: Optional[IntentProposal]):
        """Update FSM based on decision and current proposal (Week 5: uses DecisionFrame via ArmDecision)"""
        
        state = self.state_machine.state.value
        
        # Handle state transitions
        if state == 'idle':
            # Handle CONFIRM in IDLE to lock target (like L key)
            if decision.signal == DecisionSignal.CONFIRM:
                # Lock first object from world artifacts if available
                if self.world_artifacts and len(self.world_artifacts.object_ids) > 0:
                    target_id = self.world_artifacts.object_ids[0]
                    self.state_machine.set_target(target_id, locked=True)
        
        elif state == 'selecting':
            # Week 3: Proposal ready, transition to confirming (using IntentProposal)
            if proposal and proposal.action != InterfaceActionType.IDLE:
                # Convert IntentProposal to ArmProposal for state machine compatibility
                # TODO: Refactor state machine to use IntentProposal directly
                arm_action = ArmActionType(proposal.action.value)
                self.state_machine.propose_action(arm_action, proposal.description)
        
        elif state == 'confirming':
            if decision.signal == DecisionSignal.CONFIRM:  # C key - confirm action
                # Week 3: Compile plan using interface (only needs proposal and scene)
                if self.current_proposal is None:
                    print("[ORCH] No proposal to compile")
                    self.state_machine.reset()
                    return
                
                plan = self.compiler.compile(
                    self.current_proposal,
                    self.current_scene
                )
                
                if plan:  # Valid plan generated
                    self.executor.start_plan(plan)
                    self.state_machine.process_decision(decision)
                    self.trust_metrics.record_confirmation(allowed=True)
                else:
                    print("[ORCH] Compiler rejected proposal - no valid plan")
                    self.state_machine.reset()
            
            elif decision.signal == DecisionSignal.CANCEL:  # X key - cancel
                self.state_machine.process_decision(decision)
    
    def _handle_confirm(self, decision_frame: DecisionFrame):
        """Week 7: Issue token and start execution"""
        scope = self.autonomy_policy.get_token_scope()
        max_objects = self.autonomy_policy.get_max_objects()
        
        token = self.auth_manager.issue(
            source=decision_frame.source_type.value,
            quality=decision_frame.quality,
            scope=scope,
            autonomy_level=self.autonomy_policy.level.value,
            max_objects=max_objects,
        )
        
        if self.events:
            self.events.emit(
                EventType.AUTH_TOKEN_ISSUED,
                frame=self.global_frame_counter,
                data={
                    'token_id': token.token_id,
                    'scope': token.scope.value,
                    'source': token.source,
                    'quality': token.quality,
                    'autonomy_level': token.autonomy_level,
                },
            )
        
        # Start trust session
        self.trust_engine.start_session(auth_quality=decision_frame.quality)
        
        # Compile plan
        if self.current_proposal is None:
            logger.warning("[ORCH] No proposal to compile")
            self.state_machine.reset()
            return
        
        plan = self.compiler.compile(
            self.current_proposal,
            self.current_scene
        )
        
        if not plan:
            logger.warning("[ORCH] Compiler rejected proposal - no valid plan")
            self.state_machine.reset()
            return
        
        # Start execution
        self.executor.start_plan(plan)
        self._current_execution_plan = plan
        self._current_object_index = 0
        self.state_machine.start_execution()
        self._safe_pause_active = False
        self._awaiting_object_confirm = False
        self._awaiting_reauth = False
        
        # Record confirmation
        self.trust_metrics.record_confirmation(allowed=True)
    
    def _execute_task_with_trust(self, world: WorldState):
        """Week 7: Execute with trust monitoring and re-auth checks"""
        
        # Verify authorization
        if not self.auth_manager.is_authorized():
            logger.warning("[ORCH] No valid authorization! Pausing.")
            self._trigger_reauth("no_valid_token")
            return
        
        # Execute one tick
        status = self.executor.tick(world)
        
        # Week 7: Update trust from primitive results
        # Note: PrimitiveExecutor doesn't return structured results, so we infer from status
        # For now, we'll track failures via executor status
        if status == ExecutorStatus.FAILED:
            # Infer error code from context (simplified for now)
            error_code = "primitive_failed"  # Generic failure
            self.trust_engine.record_primitive_result(
                error_code=error_code,
                object_index=self._current_object_index,
            )
            
            if self.events:
                self.events.emit(
                    EventType.TRUST_UPDATED,
                    frame=self.global_frame_counter,
                    data={
                        'task_trust': self.trust_engine.task_trust,
                        'event': error_code,
                        'token_id': self.auth_manager.get_active_token_id(),
                    },
                )
        
        # Check plan completion
        if status == ExecutorStatus.COMPLETE:
            # Plan complete - check if this was an object completion
            # For now, assume single object per plan (simplified)
            self.trust_engine.record_object_complete(
                success=True,
                object_index=self._current_object_index,
            )
            self.auth_manager.record_object_started()  # Track for SINGLE_OBJECT scope
            
            # A1 mode: check if token is exhausted (single object)
            if not self.auth_manager.is_authorized():
                # Need new confirm for next object (if any remain)
                # For now, we'll complete the task
                # TODO: Check if more objects remain in multi-object scenario
                self._awaiting_object_confirm = True
                if self.events:
                    self.events.emit(
                        EventType.AUTONOMY_OBJECT_AWAIT_CONFIRM,
                        frame=self.global_frame_counter,
                        data={
                            'objects_remaining': 0,  # TODO: track remaining objects
                            'trust': self.trust_engine.task_trust,
                        },
                    )
                return
            
            # Normal completion
            self._complete_task()
            return
        
        # Check re-auth triggers
        reauth_reason = self.trust_engine.should_reauth()
        if reauth_reason:
            self._trigger_reauth(reauth_reason)
            return
        
        # Continue execution (status == RUNNING)
    
    def _handle_awaiting_object_confirm(self, decision_frame: DecisionFrame):
        """Week 7: A1 mode - waiting for confirm between objects"""
        if decision_frame.is_confirm:
            # Issue new single-object token
            token = self.auth_manager.issue(
                source=decision_frame.source_type.value,
                quality=decision_frame.quality,
                scope=AuthScope.SINGLE_OBJECT,
                autonomy_level=self.autonomy_policy.level.value,
                max_objects=1,
            )
            if self.events:
                self.events.emit(
                    EventType.AUTH_TOKEN_ISSUED,
                    frame=self.global_frame_counter,
                    data={'token_id': token.token_id, 'scope': 'single_object'},
                )
            self._awaiting_object_confirm = False
            # TODO: Resume next object execution
            # For now, we'll need to compile a new plan for the next object
            # This is simplified - in a full implementation, TaskExecutor would handle this
        
        elif decision_frame.is_cancel:
            self._complete_task_early("user_cancelled_a1")
    
    def _trigger_reauth(self, reason: str):
        """Week 7: Initiate safe pause and request re-authorization"""
        logger.warning(f"[ORCH] Re-auth triggered: {reason}")
        
        if self.events:
            self.events.emit(
                EventType.TRUST_REAUTH_TRIGGERED,
                frame=self.global_frame_counter,
                data={
                    'reason': reason,
                    'trust': self.trust_engine.task_trust,
                    'token_id': self.auth_manager.get_active_token_id(),
                },
            )
        
        # Invalidate current token
        self.auth_manager.invalidate_for_reauth(reason)
        
        # Generate safe pause primitives
        is_grasping = self.grasp.is_holding()
        self._safe_pause_primitives = self.safe_pause_helper.generate_safe_pause_primitives(
            is_grasping=is_grasping,
        )
        self._safe_pause_active = True
        
        if self.events:
            self.events.emit(
                EventType.SAFE_PAUSE_STARTED,
                frame=self.global_frame_counter,
                data={'n_primitives': len(self._safe_pause_primitives), 'is_grasping': is_grasping},
            )
    
    def _execute_safe_pause(self, world: WorldState):
        """Week 7: Execute safe pause primitives, then transition to CONFIRMING"""
        if not self._safe_pause_primitives:
            # Safe pause complete
            self._safe_pause_active = False
            if self.events:
                self.events.emit(
                    EventType.SAFE_PAUSE_COMPLETED,
                    frame=self.global_frame_counter,
                )
            # Go back to CONFIRMING — user must confirm again
            self.state_machine._transition_to(ArmUIState.CONFIRMING)
            self._awaiting_reauth = True
            return
        
        # Execute safe pause primitives via executor
        # If executor is idle, start the safe pause plan
        if self.executor.status == ExecutorStatus.IDLE:
            self.executor.start_plan(self._safe_pause_primitives)
        
        # Execute one tick
        status = self.executor.tick(world)
        
        if status == ExecutorStatus.COMPLETE:
            # Safe pause plan complete
            self._safe_pause_primitives = []
    
    def _complete_task(self):
        """Week 7: Normal task completion"""
        self.auth_manager.complete()
        self.trust_engine.end_session()
        
        if self.events:
            self.events.emit(
                EventType.AUTH_TOKEN_COMPLETED,
                frame=self.global_frame_counter,
                data={
                    'token_id': self.auth_manager.get_active_token_id(),
                    'final_trust': self.trust_engine.task_trust,
                },
            )
        
        self.state_machine.complete_execution()
        self.trust_metrics.record_execution(was_confirmed=True)
        logger.info("[ORCH] Execution complete")
    
    def _complete_task_early(self, reason: str):
        """Week 7: Early completion (cancel, etc.)"""
        self.auth_manager.invalidate(reason)
        self.trust_engine.end_session()
        self.state_machine.reset()
        logger.info(f"[ORCH] Task completed early: {reason}")
    
    def _execute_current_action(self, world: WorldState):
        """
        Execute using primitive executor (Week 1 pattern).
        Replaces Week 0's _execute_move_up, _execute_reach, etc.
        """
        status = self.executor.tick(world)
        
        # Week 3: Convert ExecutorStatus to ExecStatus for comparison
        # TODO: Refactor PrimitiveExecutor to return ExecStatus from interfaces
        if status == ExecutorStatus.COMPLETE or status.value == ExecStatus.COMPLETE.value:
            self.state_machine.complete_execution()
            self.trust_metrics.record_execution(was_confirmed=True)
            print("[ORCH] Execution complete")
        
        elif status == ExecutorStatus.FAILED or status.value == ExecStatus.FAILED.value:
            self.state_machine.reset()
            self.trust_metrics.record_execution(was_confirmed=False)
            print("[ORCH] Execution failed")
        
        # RUNNING - continue next frame
    
    def _execute_move_up(self, world: WorldState):
        """Execute MOVE_UP action with multi-frame pattern"""
        
        # Start motion (only once when not executing)
        if not self.controller.is_executing():
            # Compute target (upward from current position)
            if world.arm is None or world.arm.end_effector_position is None:
                print("[EXEC-MOVE_UP] Missing arm state, cannot execute")
                self.state_machine.complete_execution()
                return
            
            current_ee = world.arm.end_effector_position
            target = current_ee + np.array([0, 0, 0.1])  # Move up 10cm
            
            self.controller.move_to_position(target)
            print(f"[EXEC-MOVE_UP] Started motion to: {target}")
            return  # DON'T check completion same frame!
        
        # Check completion (in subsequent frames)
        if world.arm is None:
            return
        
        if self.controller.update(world.arm):
            print("[EXEC-MOVE_UP] Motion complete")
            self.state_machine.complete_execution()
            self.trust_metrics.record_execution(was_confirmed=True)
    
    def _execute_reach(self, world: WorldState):
        """Execute REACH action with multi-frame pattern"""
        
        if not self.controller.is_executing():
            if self.state_machine.target_id is None:
                print("[EXEC-REACH] No target for REACH")
                self.state_machine.complete_execution()
                return
            
            # Get target object position
            if world.object_position is None:
                print("[EXEC-REACH] Target object position not available")
                self.state_machine.complete_execution()
                return
            
            target_pos = world.object_position.copy()
            target_pos[2] += 0.05  # Hover above object
            self.controller.move_to_position(target_pos)
            print(f"[EXEC-REACH] Started motion to: {target_pos}")
            return  # DON'T check completion same frame!
        
        # Check completion (in subsequent frames)
        if world.arm is None:
            return
        
        if self.controller.update(world.arm):
            print("[EXEC-REACH] Motion complete")
            self.state_machine.complete_execution()
            self.trust_metrics.record_execution(was_confirmed=True)
    
    def _execute_grasp(self, world: WorldState):
        """Execute GRASP action."""
        print(f"[EXEC-GRASP] Starting grasp, Target: {self.state_machine.target_id}")
        if self.state_machine.target_id is None:
            return
        
        # Attach object
        success = self.grasp.attach(self.state_machine.target_id)
        print(f"[EXEC-GRASP] Grasp result: {success}")
        
        if success:
            self.state_machine.complete_execution()
            self.trust_metrics.record_execution(was_confirmed=True)
        else:
            # Grasp failed - pause
            self.state_machine.trigger_pause("Grasp failed")
    
    def _execute_place(self, world: WorldState):
        """Execute PLACE action with multi-frame pattern"""
        
        if not self.controller.is_executing():
            # Get place position from config
            robot_config = self.config.get('robot', {})
            place_pos = robot_config.get('place_position', [0.0, 0.0, 0.65])
            self.controller.move_to_position(np.array(place_pos))
            print(f"[EXEC-PLACE] Started motion to: {place_pos}")
            return  # DON'T check completion same frame!
        
        # Check completion (in subsequent frames)
        if world.arm is None:
            return
        
        if self.controller.update(world.arm):
            print("[EXEC-PLACE] Motion complete, detaching object")
            self.grasp.detach()
            self.state_machine.complete_execution()
            self.trust_metrics.record_execution(was_confirmed=True)
    
    def _create_snapshot(self, world: WorldState) -> UISnapshot:
        """Create UI snapshot with Week 1 scene info"""
        # Build objects list for Week 1 (if needed)
        objects_list = None
        if hasattr(world, 'objects') and world.objects:
            objects_list = world.objects
        elif world.object is not None:
            objects_list = [world.object] if world.object.visible else []
        
        return UISnapshot(
            state=self.state_machine.state,
            frame_count=self.global_frame_counter,
            timestamp=time.time(),
            target_id=self.state_machine.target_id,
            target_locked=self.state_machine.target_locked,
            proposal=self.current_proposal if self.current_proposal else self.state_machine.proposal,
            holding_object=self.grasp.is_holding(),
            attached_id=self.grasp.get_attached_id(),
            false_executions=self.trust_metrics.false_executions,
            paused=self.state_machine.paused,
            pause_reason=self.state_machine.pause_reason,
            what_happened="",  # Can be populated if needed
            # NEW Week 1 fields
            scene_summary=self.current_scene,
            executor_status=self.executor.status if self.executor else None,
            primitive_index=self.executor.plan_index if self.executor else 0,
            arm_state=world.arm,
            objects=objects_list,
            current_proposal=self.current_proposal,
            # Week 4: Proposer statistics
            proposer_stats=self.proposer_registry.get_stats() if self.proposer_registry else None,
            # Week 7: Authorization, Trust, Autonomy
            autonomy_level=self.autonomy_policy.level.value if self.autonomy_policy else None,
            task_trust=self.trust_engine.task_trust if self.trust_engine else None,
            auth_token_id=self.auth_manager.get_active_token_id() if self.auth_manager else None,
            awaiting_reauth=self._awaiting_reauth,
            awaiting_object_confirm=self._awaiting_object_confirm,
        )
    
    def force_lock_target(self, object_id: int):
        """Manually lock target (L key)."""
        if self.sim.is_valid_object(object_id):
            self.state_machine.set_target(object_id, locked=True)
            print(f"[ORCH] Forced lock: {object_id}")
    
    def close(self):
        """Cleanup."""
        self.sim.close()
        print("[ORCH] Closed")

