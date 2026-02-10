from typing import List, Optional
from enum import Enum
import numpy as np
from src.planning.primitive import Primitive, PrimitiveType
from src.robot.world_state import WorldState
from src.robot.controller import RobotController
from src.robot.grasp import GraspController

class ExecutorStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"

class PrimitiveExecutor:
    """
    Executes primitive plans multi-frame using Week 0's controller pattern.
    
    Critical: Uses same multi-frame semantics as Week 0 orchestrator.
    """
    
    def __init__(self, controller: RobotController, grasp: GraspController):
        self.controller = controller
        self.grasp = grasp
        
        # Execution state
        self.active_plan: List[Primitive] = []
        self.plan_index: int = 0
        self.active_primitive_started: bool = False
        self.status: ExecutorStatus = ExecutorStatus.IDLE
    
    def start_plan(self, plan: List[Primitive]):
        """Begin executing a new plan"""
        self.active_plan = plan
        self.plan_index = 0
        self.active_primitive_started = False
        self.status = ExecutorStatus.RUNNING if plan else ExecutorStatus.IDLE
        
        print(f"[EXECUTOR] Started plan with {len(plan)} primitives")
    
    def tick(self, world: WorldState) -> ExecutorStatus:
        """
        Execute one frame of the current plan.
        
        Returns:
            Current status (RUNNING, COMPLETE, FAILED)
        """
        # No active plan
        if not self.active_plan:
            self.status = ExecutorStatus.IDLE
            return self.status
        
        # Plan complete
        if self.plan_index >= len(self.active_plan):
            print("[EXECUTOR] Plan complete!")
            self.status = ExecutorStatus.COMPLETE
            return self.status
        
        # Execute current primitive
        primitive = self.active_plan[self.plan_index]
        
        # Multi-frame pattern (Week 0 lesson!)
        if not self.active_primitive_started:
            # Start primitive (frame 1)
            success = self._start_primitive(primitive, world)
            
            if not success:
                print(f"[EXECUTOR] Failed to start primitive {self.plan_index}: {primitive.type}")
                self.status = ExecutorStatus.FAILED
                return self.status
            
            self.active_primitive_started = True
            self.status = ExecutorStatus.RUNNING
            return self.status  # Don't check completion same frame!
        
        # Check completion (frame 2+)
        if self._check_primitive_complete(primitive, world):
            print(f"[EXECUTOR] Primitive {self.plan_index} complete: {primitive.type}")
            self.plan_index += 1
            self.active_primitive_started = False
            # Continue to next primitive next frame
        
        self.status = ExecutorStatus.RUNNING
        return self.status
    
    def _start_primitive(self, primitive: Primitive, world: WorldState) -> bool:
        """
        Start executing a primitive (called once per primitive).
        
        Returns:
            True if started successfully, False if failed
        """
        if primitive.type in [PrimitiveType.REACH, PrimitiveType.MOVE_TO]:
            # Use controller from Week 0
            if primitive.target_xyz is None:
                return False
            
            self.controller.move_to_position(primitive.target_xyz)
            return True
        
        elif primitive.type == PrimitiveType.GRASP:
            # Use grasp controller
            if primitive.object_id is None:
                return False
            
            self.grasp.attach(primitive.object_id)
            return True
        
        elif primitive.type == PrimitiveType.RELEASE:
            # Release grasp
            if primitive.object_id is None:
                return False
            
            self.grasp.detach()
            return True
        
        else:
            print(f"[EXECUTOR] Unknown primitive type: {primitive.type}")
            return False
    
    def _check_primitive_complete(self, primitive: Primitive, world: WorldState) -> bool:
        """
        Check if primitive has finished executing.
        
        Returns:
            True if complete, False if still running
        """
        if primitive.type in [PrimitiveType.REACH, PrimitiveType.MOVE_TO]:
            # Check controller convergence (Week 0 pattern)
            if world.arm is None:
                return False
            return self.controller.update(world.arm)
        
        elif primitive.type == PrimitiveType.GRASP:
            # Check if grasp constraint exists
            # For Week 1, assume grasp completes in 1 frame
            return True
        
        elif primitive.type == PrimitiveType.RELEASE:
            # Release completes immediately
            return True
        
        return False
    
    def is_executing(self) -> bool:
        """Check if executor is currently running a plan"""
        return self.status == ExecutorStatus.RUNNING
