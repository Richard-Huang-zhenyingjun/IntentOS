"""Main orchestrator - single coordinator for entire system."""

import time
from typing import Optional
from src.core.schema import ArmDecision, DecisionSignal, UISnapshot, ArmActionType
from src.core.state_machine import StateMachine
from src.core.trust_metrics import TrustMetrics
from src.input.decision_source import DecisionSource
from src.robot.simulator import RobotSimulator
from src.robot.controller import RobotController
from src.robot.grasp import GraspController
from src.robot.world_state import WorldState
from src.planning.planner import ActionPlanner
from src.recovery.pause_controller import PauseController


class Orchestrator:
    """Main system coordinator - SELECT→PROPOSE→CONFIRM→EXECUTE."""
    
    def __init__(self, config: dict, decision_source: DecisionSource, sim: RobotSimulator):
        self.config = config
        
        # Input
        self.decision_source = decision_source
        
        # Robot
        self.sim = sim
        self.controller = RobotController(config, sim)
        self.grasp = GraspController(sim)
        
        # Planning
        self.planner = ActionPlanner(config)
        
        # State
        self.state_machine = StateMachine()
        self.trust_metrics = TrustMetrics()
        
        # Recovery
        self.pause_controller = PauseController(config)
        
        # Frame tracking
        self.frame_count = 0
        self.start_time = time.time()
        
        print("[ORCH] ✓ Orchestrator initialized")
        print(f"[ORCH]   Input: {decision_source.get_source_name()}")
    
    def step(self) -> UISnapshot:
        """Main control loop - called once per frame.
        
        Returns:
            UISnapshot for rendering
        """
        self.frame_count += 1
        timestamp = time.time()
        
        # 1. Step simulation
        self.sim.step()
        
        # 2. Read world state
        world_state = self._read_world_state()
        
        # 3. Read input decision (SINGLE READ POINT)
        decision = self.decision_source.read_decision()
        
        # 4. Check for pause conditions
        if self.pause_controller.should_pause(world_state, self.state_machine):
            reason = self.pause_controller.get_pause_reason()
            self.state_machine.trigger_pause(reason)
            self.trust_metrics.record_pause()
        
        # 5. State machine update
        what_happened = self._update_state_machine(world_state, decision)
        
        # 6. Execute if needed
        if self.state_machine.state.value == 'executing':
            self._execute_current_action(world_state)
        
        # 7. Tick state machine
        self.state_machine.tick()
        
        # 8. Build UI snapshot
        snapshot = self._build_snapshot(world_state, what_happened, timestamp)
        
        return snapshot
    
    def _read_world_state(self) -> WorldState:
        """Read current world state from simulator."""
        return WorldState(
            arm=self.sim.get_arm_state(),
            object=self.sim.get_object_state(),
            target_id=self.state_machine.target_id,
            holding=self.grasp.is_holding(),
            attached_id=self.grasp.get_attached_id()
        )
    
    def _update_state_machine(self, world: WorldState, decision: ArmDecision) -> str:
        """Update state machine based on world + decision.
        
        Returns:
            Human-readable event description
        """
        state = self.state_machine.state.value
        
        # IDLE: Looking for target
        if state == 'idle':
            if world.target_id is not None:
                self.state_machine.set_target(world.target_id, locked=True)
                return f"Target locked: {world.target_id}"
            return "Waiting for target"
        
        # SELECTING: Planning action
        elif state == 'selecting':
            if self.state_machine.target_id is None:
                self.state_machine.reset()
                return "Target lost"
            
            # Propose next action
            action = self.planner.propose_next_action(world)
            if action:
                reason = self.planner.get_action_reason(action, world)
                self.state_machine.propose_action(action, reason)
                return f"Proposed: {action.value}"
            else:
                return "No actions available"
        
        # CONFIRMING: Awaiting decision
        elif state == 'confirming':
            if decision.signal == DecisionSignal.CONFIRM:
                # CRITICAL: Record confirmation
                self.trust_metrics.record_confirmation(allowed=True)
                
                # Transition to EXECUTING
                allowed = self.state_machine.process_decision(decision)
                if allowed:
                    return f"✓ Confirmed: {self.state_machine.proposal.action.value}"
            
            elif decision.signal == DecisionSignal.CANCEL:
                self.state_machine.process_decision(decision)
                return "✗ Cancelled"
            
            return f"Awaiting confirm for {self.state_machine.proposal.action.value}"
        
        # EXECUTING: Action in progress
        elif state == 'executing':
            # Controller handles this
            return f"Executing {self.state_machine.proposal.action.value}"
        
        # DONE: Action complete
        elif state == 'done':
            # Reset to selecting for next action
            self.state_machine.set_target(self.state_machine.target_id, locked=True)
            return "Ready for next action"
        
        # PAUSED: Recovery needed
        elif state == 'paused':
            # User must manually resume (for now)
            return f"PAUSED: {self.state_machine.pause_reason}"
        
        return f"State: {state}"
    
    def _execute_current_action(self, world: WorldState):
        """Execute the currently proposed action."""
        if self.state_machine.proposal is None:
            return
        
        action = self.state_machine.proposal.action
        
        # Dispatch to appropriate executor
        if action == ArmActionType.MOVE_UP:
            self._execute_move_up(world)
        elif action == ArmActionType.REACH:
            self._execute_reach(world)
        elif action == ArmActionType.GRASP:
            self._execute_grasp(world)
        elif action == ArmActionType.PLACE:
            self._execute_place(world)
    
    def _execute_move_up(self, world: WorldState):
        """Execute MOVE_UP action."""
        if world.ee_position is None:
            return
        
        target = world.ee_position.copy()
        target[2] = 0.3  # Move to safe height
        
        self.controller.move_to_position(target)
        
        # Check if complete
        if self.controller.update(world.arm):
            self.state_machine.complete_execution()
            self.trust_metrics.record_execution(was_confirmed=True)
    
    def _execute_reach(self, world: WorldState):
        """Execute REACH action."""
        if world.object_position is None:
            return
        
        # Move to object position (slightly above)
        target = world.object_position.copy()
        target[2] += 0.05  # Hover above
        
        self.controller.move_to_position(target)
        
        # Check if complete
        if self.controller.update(world.arm):
            self.state_machine.complete_execution()
            self.trust_metrics.record_execution(was_confirmed=True)
    
    def _execute_grasp(self, world: WorldState):
        """Execute GRASP action."""
        if self.state_machine.target_id is None:
            return
        
        # Attach object
        success = self.grasp.attach(self.state_machine.target_id)
        
        if success:
            self.state_machine.complete_execution()
            self.trust_metrics.record_execution(was_confirmed=True)
        else:
            # Grasp failed - pause
            self.state_machine.trigger_pause("Grasp failed")
    
    def _execute_place(self, world: WorldState):
        """Execute PLACE action."""
        # Move to place location
        place_pos = self.config.get('place_position', [0.0, 0.0, 0.65])
        self.controller.move_to_position(place_pos)
        
        # Check if arrived
        if self.controller.update(world.arm):
            # Release object
            self.grasp.detach()
            self.state_machine.complete_execution()
            self.trust_metrics.record_execution(was_confirmed=True)
    
    def _build_snapshot(self, world: WorldState, what_happened: str, timestamp: float) -> UISnapshot:
        """Build UI snapshot for rendering."""
        return UISnapshot(
            # State
            state=self.state_machine.state,
            frame_count=self.frame_count,
            timestamp=timestamp,
            
            # Target
            target_id=self.state_machine.target_id,
            target_locked=self.state_machine.target_locked,
            
            # Proposal
            proposal=self.state_machine.proposal,
            
            # Grasp
            holding_object=self.grasp.is_holding(),
            attached_id=self.grasp.get_attached_id(),
            
            # Safety
            false_executions=self.trust_metrics.false_executions,
            paused=self.state_machine.paused,
            pause_reason=self.state_machine.pause_reason,
            
            # Metadata
            what_happened=what_happened
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

