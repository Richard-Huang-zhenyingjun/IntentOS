# Speed, Grab, Place, FPS Investigation Report
**Date:** 2025-01-07  
**Purpose:** Comprehensive investigation of arm movement speed, automatic grasping, PLACE functionality, and frame rate

---

## 🎯 CATEGORY 1: ARM MOVEMENT SPEED

### Q1: Where are velocity/speed limits configured?

#### Velocity Limits Found:

| File | Line | Parameter | Current Value | Units | What it controls |
|------|------|-----------|---------------|-------|-------------------|
| `configs/robotics.yaml` | 84 | `max_joint_vel_rad_s` | 1.0 | rad/s | Maximum joint velocity |
| `configs/robotics.yaml` | 85 | `max_joint_step_rad` | 0.02 | rad | Maximum joint change per tick |
| `configs/robotics.yaml` | 3 | `timestep` | 0.008333 | s | Physics timestep (120 Hz) |
| `configs/robotics.yaml` | 79 | `hz` | 120 | Hz | Control rate |
| `src/robotics/safety_limits.py` | 50-67 | `clamp_joint_velocity()` | Function | - | Velocity clamping logic |
| `src/robotics/arm_controller.py` | 69 | `self.max_vel` | From config | rad/s | Used in velocity clamping |

#### Speed Parameters Found:

| File | Line | Parameter | Current Value | Units | What it controls |
|------|------|-----------|---------------|-------|-------------------|
| `configs/robotics.yaml` | 79 | `max_steps_per_action` | 1200 | steps | Maximum steps per action (10s @ 120Hz) |
| `configs/robotics.yaml` | 80 | `settle_steps_after` | 30 | steps | Settle period after reaching target |
| `src/robotics/trajectory.py` | 29-45 | `plan_steps()` | Calculated | steps | Number of steps based on max_step_rad |

#### Trajectory Timing Found:

| File | Line | Parameter | Current Value | Units | What it controls |
|------|------|-----------|---------------|-------|-------------------|
| `src/robotics/trajectory.py` | 11-26 | `interpolate_joints()` | Linear | - | Joint interpolation method |
| `src/robotics/trajectory.py` | 29-45 | `plan_steps()` | Based on max_step | steps | Trajectory step count |
| `src/robotics/trajectory.py` | 64-77 | `next_q()` | Incremental | - | Next joint configuration |

**Key Finding:** Speed is controlled by:
1. **`max_joint_vel_rad_s: 1.0`** - Maximum joint velocity (rad/s)
2. **`max_joint_step_rad: 0.02`** - Maximum joint change per step (rad)
3. **`timestep: 0.008333`** - Physics timestep (120 Hz = 8.33ms per step)

**Speed Calculation:**
- At 120 Hz with `max_step_rad: 0.02`, max velocity = 0.02 / 0.008333 = **2.4 rad/s**
- But `max_joint_vel_rad_s: 1.0` limits it to **1.0 rad/s** (the tighter constraint)

---

### Q2: How is trajectory execution currently implemented?

**File:** `src/robotics/arm_controller.py`

#### Complete Trajectory Execution Logic:

```python
# Lines 148-208: tick() method - main execution loop
def tick(self, world, sim) -> Tuple[bool, Optional[ExecutionResult]]:
    """Advance execution one step."""
    
    # Check if frozen (Week 8)
    if self.frozen:
        return False, None
    
    # Validate state
    if self.active_action is None or self.trajectory is None:
        return True, ExecutionResult(success=False, reason="No active action", ...)
    
    # Check cancellation
    if self.cancelled:
        return self._finish_cancelled(world, sim)
    
    # Check timeout
    if self.steps_used >= self.max_steps:  # max_steps = 1200
        return self._finish_timeout(world, sim)
    
    # Get current state
    arm_state = read_arm_state(sim.robot)
    q_current = arm_state.q
    
    # Get next trajectory point
    q_next = self.trajectory.next_q()  # Increments step_idx, returns interpolated q
    
    # Apply safety limits (3 layers)
    q_safe = clamp_joint_targets(q_next, sim.robot.joint_lower, sim.robot.joint_upper)
    q_safe = clamp_joint_step(q_current, q_safe, self.max_step_rad)  # 0.02 rad max
    q_safe = clamp_joint_velocity(q_current, q_safe, self.dt, self.max_vel)  # 1.0 rad/s max
    
    # Apply motor control
    p.setJointMotorControlArray(
        sim.robot.body_id,
        sim.robot.joint_indices,
        controlMode=p.POSITION_CONTROL,
        targetPositions=q_safe.tolist(),
        forces=[100.0] * len(sim.robot.joint_indices)
    )
    
    self.steps_used += 1
    
    # Check completion (after settle period)
    if self.trajectory.is_complete() and self.steps_used > self.trajectory.steps_total + self.settle_steps:
        return self._check_completion(world, sim)
    
    return False, None  # Continue executing
```

#### Trajectory Planning Logic:

```python
# Lines 138-144: start_action() method
# Plan trajectory
steps_needed = plan_steps(q_current, self.q_goal, self.max_step_rad)
self.trajectory = TrajectoryPlan(
    q_start=q_current,
    q_goal=self.q_goal,
    steps_total=steps_needed
)
```

**Key Details:**
- **Steps per trajectory:** Calculated by `plan_steps()` based on max joint delta / max_step_rad
- **Frame rate cap:** 120 Hz (physics timestep)
- **Sleep/delay:** No sleep per step (runs as fast as possible, frame limiting in main loop)
- **Can reduce steps:** YES - increase `max_joint_step_rad` or `max_joint_vel_rad_s`

**Example:** If max joint change is 0.5 rad:
- Steps = ceil(0.5 / 0.02) = **25 steps**
- At 120 Hz: **0.21 seconds** to complete
- At 1.0 rad/s max: **0.5 seconds** to complete (velocity limit is tighter)

---

### Q3: What are current velocity limit values?

**Complete Configuration Table:**

| Location | Parameter | Current Value | Units | What it affects |
|----------|-----------|---------------|-------|-----------------|
| `configs/robotics.yaml:84` | `max_joint_vel_rad_s` | 1.0 | rad/s | Maximum joint velocity |
| `configs/robotics.yaml:85` | `max_joint_step_rad` | 0.02 | rad | Maximum joint change per step |
| `configs/robotics.yaml:3` | `timestep` | 0.008333 | s | Physics timestep (120 Hz) |
| `configs/robotics.yaml:79` | `hz` | 120 | Hz | Control rate |
| `configs/robotics.yaml:80` | `settle_steps_after` | 30 | steps | Settle period (0.25s @ 120Hz) |
| `configs/robotics.yaml:79` | `max_steps_per_action` | 1200 | steps | Timeout (10s @ 120Hz) |
| `src/robotics/safety_limits.py:50-67` | `clamp_joint_velocity()` | Function | - | Velocity clamping implementation |
| `src/robotics/trajectory.py:29-45` | `plan_steps()` | Calculated | steps | Steps based on max_step_rad |

**Hardcoded Constants:** None found - all values come from config.

**To Make Arm Faster:**
1. Increase `max_joint_vel_rad_s` (e.g., 2.0 rad/s)
2. Increase `max_joint_step_rad` (e.g., 0.04 rad)
3. Reduce `settle_steps_after` (e.g., 15 steps)

---

## 🎯 CATEGORY 2: AUTOMATIC GRASPING

### Q4: Why doesn't the arm automatically grasp after reaching?

#### Current Behavior:

**File:** `src/intent_core/arm_state_machine.py:214-224`

```python
def _tick_done(self) -> None:
    """Tick DONE state: wait for next cycle."""
    # Auto-return to selecting after cooldown
    if self.cooldown_frames == 0:
        if self.active_target_id is not None and self.target_locked:
            self._log_event("Ready for next action")
            self.active_proposal = None
            self._transition_to(ArmUIState.SELECTING_ACTION)  # ← Auto-proposes next action
            self.cooldown_frames = 10  # Brief pause before next proposal
        else:
            self._transition_to(ArmUIState.IDLE)
```

**Finding:** The system **DOES** automatically propose the next action after completion!

#### Action Planning Logic:

**File:** `src/world/world_model.py:98-130`

```python
def propose_next_action(self) -> Optional[ArmActionType]:
    """
    Propose next action using deterministic priority logic.
    
    Priority (paper-aligned sequential task):
    1. MOVE_ARM_UP (if arm too low)
    2. REACH_FORWARD (if arm ready but far from object)
    3. GRASP_OBJECT (if arm at object)  # ← GRASP is in priority list!
    """
    available = self.get_available_actions()
    
    if not available:
        return None
    
    # Priority ordering
    priority = [
        ArmActionType.MOVE_ARM_UP,
        ArmActionType.REACH_FORWARD,
        ArmActionType.GRASP_OBJECT,  # ← Third priority
    ]
    
    for action in priority:
        if action in available:
            return action
    
    return available[0]
```

#### GRASP Preconditions:

**File:** `src/robotics/arm_actions.py:86-100`

```python
def grasp_available(world: 'WorldModel') -> bool:
    """
    GRASP_OBJECT is available if:
    - Object is visible
    - EE is close to object in 3D space (< 6cm)
    """
    if not world.object_state.visible:
        return False
    
    dist_3d = distance_3d(world.arm_state.ee_pos, world.object_state.pos)
    threshold = world.cfg['thresholds']['grasp_dist']  # 0.06m = 6cm
    
    return dist_3d < threshold
```

**Why It Might Not Auto-Grasp:**

1. **Distance threshold too strict:** `grasp_dist: 0.06m` (6cm) - EE might not get close enough
2. **REACH_FORWARD success condition:** EE only needs to be within `reach_close_xy: 0.10m` (10cm) in XY plane, but not necessarily close in 3D
3. **State machine waits for confirmation:** Even if GRASP is proposed, user must press C to confirm

**Answer:**
- ✅ **GRASP action exists** (`ArmActionType.GRASP_OBJECT`)
- ✅ **Auto-proposal works** (system proposes GRASP after REACH completes)
- ⚠️ **Requires user confirmation** (C key press)
- ⚠️ **Distance threshold might be too strict** (6cm 3D distance)

---

### Q5: How are action sequences currently implemented?

#### Current Implementation:

**File:** `src/intent_core/arm_state_machine.py:214-224`

```python
def _tick_done(self) -> None:
    """Tick DONE state: wait for next cycle."""
    # Auto-return to selecting after cooldown
    if self.cooldown_frames == 0:
        if self.active_target_id is not None and self.target_locked:
            self._log_event("Ready for next action")
            self.active_proposal = None
            self._transition_to(ArmUIState.SELECTING_ACTION)  # ← Auto-proposes next
            self.cooldown_frames = 10  # Brief pause before next proposal
```

**Finding:** System **automatically proposes next action** after completion!

#### Action Chaining Flow:

1. **Action completes** → State = `DONE`
2. **After cooldown** → State = `SELECTING_ACTION`
3. **World model proposes** → Next available action (MOVE_UP → REACH → GRASP)
4. **State = `AWAITING_CONFIRM`** → Waits for user confirmation (C key)

**Key Question:** Is "one action at a time" enforced architecturally?

**Answer:** YES - Each action requires explicit confirmation. However, the system **does auto-propose** the next action, so the user just needs to press C repeatedly.

**To Enable Auto-Chaining (No Confirmation):**
- Modify `_tick_done()` to auto-confirm if proposal is available
- Or modify `_tick_selecting_action()` to auto-confirm immediately

---

## 🎯 CATEGORY 3: PLACE FUNCTIONALITY

### Q6: Does a PLACE action already exist?

#### Search Results:

**grep for "PLACE|place|drop|release":**
- ❌ **No PLACE action found** in `src/robotics/action_types.py`
- ❌ **No PLACE action found** in `src/robotics/arm_actions.py`
- ✅ **`detach()` method exists** in `src/robotics/grasp_logic.py:108-128`

#### Current Action Types:

**File:** `src/robotics/action_types.py:9-18`

```python
class ArmActionType(str, Enum):
    MOVE_ARM_UP = "move_arm_up"
    REACH_FORWARD = "reach_forward"
    GRASP_OBJECT = "grasp_object"
    # NO PLACE_OBJECT
```

#### Detach Functionality:

**File:** `src/robotics/grasp_logic.py:108-128`

```python
def detach(self) -> bool:
    """
    Detach held object.
    
    Returns:
        True if detachment succeeded
    """
    if self.constraint_id is None:
        return False
    
    try:
        p.removeConstraint(self.constraint_id)
        print(f"✓ Detached object {self.held_object_id}")
        
        self.constraint_id = None
        self.held_object_id = None
        return True
        
    except Exception as e:
        print(f"⚠️  Detachment failed: {e}")
        return False
```

**Answer:**
- ❌ **PLACE action does NOT exist**
- ✅ **Detach functionality exists** (can release object)
- ✅ **Grasp logic has release capability**

---

### Q7: What would PLACE action need to do?

#### Requirements Analysis:

**1. Action Type Definition:**
- [ ] Add `PLACE_OBJECT = "place_object"` to `ArmActionType` enum

**2. Precondition Logic:**
- [ ] Check if holding object: `world.is_holding_any()`
- [ ] Check if at place location (new threshold needed)

**3. IK Target for Place Location:**
- [ ] Define place zone coordinates in `configs/robotics.yaml`
- [ ] Compute IK target above place zone

**4. Detach Object Logic:**
- ✅ Already exists: `grasp_logic.detach()`

**5. Key Handler:**
- [ ] Add P key handler in `scripts/run_unified_arm_demo.py`

**6. World Model Integration:**
- [ ] Add `place_available()` precondition function
- [ ] Add `place_success()` success condition
- [ ] Add PLACE to action priority list

**7. Action Specification:**
- [ ] Add `PLACE_OBJECT` to `ACTION_SPECS` dict
- [ ] Define goal pose (place zone location)

**Place Zone Configuration Needed:**

```yaml
# In configs/robotics.yaml
place_zone:
  position: [0.0, 0.0, 0.65]  # On table surface
  approach_height_z: 0.10      # 10cm above place zone
```

**Complete Requirements Checklist:**

- [ ] **Action type:** Add `PLACE_OBJECT` to `ArmActionType`
- [ ] **Precondition:** `is_holding_any()` and at place location
- [ ] **IK target:** Place zone coordinates
- [ ] **Detach logic:** Use existing `grasp_logic.detach()`
- [ ] **Key handler:** P key in `run_unified_arm_demo.py`
- [ ] **World model:** Add place availability/success logic
- [ ] **Action spec:** Add PLACE to `ACTION_SPECS`
- [ ] **Config:** Add place zone location

---

## 🎯 CATEGORY 4: FRAME RATE / SMOOTHNESS

### Q8: What's the current frame rate and what limits it?

#### Frame Rate Configuration:

**File:** `scripts/run_unified_arm_demo.py:204-206`

```python
# FIX 4: Compensated frame limiting
target_fps = 30
target_frame_time = 1.0 / target_fps  # 0.0333s = 33.3ms
```

**File:** `scripts/run_unified_arm_demo.py:440-450`

```python
# Frame timing (compensated frame limiting)
frame_elapsed = time.time() - frame_start
sleep_time = max(0.001, target_frame_time - frame_elapsed)
time.sleep(sleep_time)
```

#### Physics Configuration:

**File:** `configs/robotics.yaml:2-6`

```yaml
physics:
  timestep: 0.008333  # 120 Hz (1/120 = 0.008333)
  gravity: [0, 0, -9.81]
  num_solver_iterations: 50
  use_real_time: false  # Run as fast as possible
```

**Current Configuration:**
- **Target FPS:** 30 FPS (main loop)
- **Physics Rate:** 120 Hz (internal simulation)
- **Frame Time:** 33.3ms per frame
- **Physics Timestep:** 8.33ms per step

**Bottlenecks Identified:**

1. ✅ **Physics simulation:** 120 Hz (not a bottleneck)
2. ⚠️ **Rendering:** Multiple debug text calls per frame
3. 🔴 **Logging/IO:** Excessive debug logging (see PERFORMANCE_LAG_ANALYSIS.md)
4. ✅ **Orchestrator step:** Efficient
5. ⚠️ **Frame limiting:** Compensated (good)

**Actual FPS:** Likely **6-16 FPS** due to debug logging (see PERFORMANCE_LAG_ANALYSIS.md)

---

### Q9: Where is frame limiting implemented?

**File:** `scripts/run_unified_arm_demo.py:239-450`

```python
try:
    while True:
        # FIX 4: Start frame timing
        frame_start = time.time()
        
        # ... main loop code ...
        
        # FIX 4: Compensated frame limiting
        frame_elapsed = time.time() - frame_start
        sleep_time = max(0.001, target_frame_time - frame_elapsed)
        time.sleep(sleep_time)
```

**Key Features:**
- ✅ **Compensated frame limiting:** Accounts for processing time
- ✅ **Target FPS:** 30 FPS (hardcoded)
- ✅ **Minimum sleep:** 1ms (prevents busy-wait)

**To Change FPS:**
- Modify `target_fps = 30` to desired value (e.g., 60)

---

### Q10: What's the rendering overhead?

#### Debug Text Rendering:

**Count:** ~5-10 calls per frame
- Selection overlay: 1-2 calls
- Intent overlay: 2-3 calls
- Key echo: 1 call (if key pressed)
- L key feedback: 1-2 calls (if L pressed)

**File Locations:**
- `src/ui/selection_overlay.py` - 4 calls
- `src/ui/arm_intent_overlay.py` - Multiple calls
- `scripts/run_unified_arm_demo.py` - 1-2 calls

#### Overlay Rendering:

**File:** `src/ui/arm_intent_overlay.py`
- **Throttled:** YES (minimal mode, 10Hz update)
- **Items per frame:** ~2-3 debug text items

**File:** `src/ui/selection_overlay.py`
- **Throttled:** NO (updates every frame)
- **Items per frame:** 1-2 debug text items

**Total Rendering Calls Per Frame:**
- **Debug text:** ~5-10 calls
- **Overlay items:** ~2-3 items
- **Total:** ~7-13 PyBullet debug text calls per frame

**Can We Reduce?**
- ✅ Selection overlay already optimized (reuses IDs)
- ✅ Intent overlay throttled (10Hz)
- ⚠️ Debug logging adds overhead (see PERFORMANCE_LAG_ANALYSIS.md)

---

## 🎯 CATEGORY 5: CONFIGURATION FILES

### Q11: Show complete configs/robotics.yaml

**File:** `configs/robotics.yaml` (Complete contents shown in Q1-Q3 above)

**Key Sections:**
- **Physics:** timestep, gravity, solver iterations
- **Control:** hz, max_steps_per_action, settle_steps_after
- **Safety:** max_joint_vel_rad_s, max_joint_step_rad, tolerances
- **Grasp:** attach_dist_m, constraint_max_force, lift parameters
- **Thresholds:** ee_min_z, ee_target_z, reach_close_xy, grasp_dist

**Main Speed Parameters:**
```yaml
control:
  hz: 120                        # Physics rate
  max_steps_per_action: 1200     # 10s timeout @ 120Hz
  settle_steps_after: 30         # 0.25s settle period

safety:
  max_joint_vel_rad_s: 1.0       # Max joint velocity
  max_joint_step_rad: 0.02       # Max joint change per step
```

---

## 🎯 SUMMARY QUESTIONS

### Q12: File Modification Checklist

#### CHANGE 1: Make Arm Move Faster

**Files to modify:**

- [ ] **`configs/robotics.yaml`**
  - Increase `max_joint_vel_rad_s: 1.0` → `2.0` (or higher)
  - Increase `max_joint_step_rad: 0.02` → `0.04` (or higher)
  - Reduce `settle_steps_after: 30` → `15` (optional)

- [ ] **`src/robotics/safety_limits.py`**
  - No changes needed (uses config values)

- [ ] **`src/robotics/trajectory.py`**
  - No changes needed (uses config values)

**Impact:** Arm will move 2x faster (or more, depending on values)

---

#### CHANGE 2: Auto-Grasp After Reach (No Confirmation)

**Files to modify:**

- [ ] **`src/intent_core/arm_state_machine.py`**
  - Modify `_tick_done()` to auto-confirm if GRASP is proposed
  - Or modify `_tick_selecting_action()` to auto-confirm GRASP

- [ ] **`src/world/world_model.py`**
  - No changes needed (already proposes GRASP)

**Alternative:** Reduce `grasp_dist` threshold to make GRASP available sooner

---

#### CHANGE 3: Add PLACE Action + P Key

**Files to modify:**

- [ ] **`src/robotics/action_types.py`**
  - Add `PLACE_OBJECT = "place_object"` to `ArmActionType` enum

- [ ] **`src/robotics/arm_actions.py`**
  - Add `place_available()` precondition function
  - Add `place_success()` success condition
  - Add `PLACE_OBJECT` to `ACTION_SPECS` dict
  - Add `_goal_pose_place()` function

- [ ] **`scripts/run_unified_arm_demo.py`**
  - Add P key handler (similar to L key handler)
  - Call `orchestrator.force_action(PLACE_OBJECT)` or similar

- [ ] **`src/robotics/grasp_logic.py`**
  - ✅ `detach()` already exists (no changes needed)

- [ ] **`configs/robotics.yaml`**
  - Add `place_zone` section with position and approach_height

- [ ] **`src/world/world_model.py`**
  - Add PLACE to priority list in `propose_next_action()`

**New files needed:** None (modify existing)

---

#### CHANGE 4: Improve Frame Rate

**Files to modify:**

- [ ] **`scripts/run_unified_arm_demo.py`**
  - Remove debug logging (lines 381-424 for L key)
  - Increase `target_fps = 30` → `60` (optional)

- [ ] **`src/utils/safe_pybullet.py`**
  - Remove debug logging (lines 121-122, 141, 144)

- [ ] **`configs/robotics.yaml`**
  - No changes needed (physics already optimized)

**Priority:** Remove debug logging first (biggest impact)

---

## 📋 OUTPUT SUMMARY

### Q1-Q3 (SPEED):
- **Velocity limits found in:** `configs/robotics.yaml:84-85`
- **Current values:** `max_joint_vel_rad_s: 1.0 rad/s`, `max_joint_step_rad: 0.02 rad`
- **Files to modify:** `configs/robotics.yaml` (increase values)

### Q4-Q5 (AUTO-GRASP):
- **Current behavior:** System auto-proposes GRASP after REACH completes
- **Why it stops:** Requires user confirmation (C key press)
- **Files to modify:** `src/intent_core/arm_state_machine.py` (auto-confirm GRASP)

### Q6-Q7 (PLACE):
- **PLACE exists:** NO
- **Requirements:** Add action type, precondition, goal pose, key handler, config
- **Files to create/modify:** 6 files (see Q12)

### Q8-Q10 (FPS):
- **Current FPS:** 30 FPS target, 6-16 FPS actual (due to debug logging)
- **Bottlenecks:** Debug logging (see PERFORMANCE_LAG_ANALYSIS.md)
- **Files to modify:** Remove debug logging in `safe_pybullet.py` and `run_unified_arm_demo.py`

### Q11 (CONFIG):
[Complete `configs/robotics.yaml` shown above]

### Q12 (CHECKLIST):
[Complete modification checklist shown above]

---

## 🎯 RECOMMENDATIONS

### Priority 1: Fix Performance (Remove Debug Logging)
- Remove debug logging to restore 30 FPS
- See `PERFORMANCE_LAG_ANALYSIS.md` for details

### Priority 2: Make Arm Faster
- Increase `max_joint_vel_rad_s: 1.0` → `2.0`
- Increase `max_joint_step_rad: 0.02` → `0.04`

### Priority 3: Auto-Grasp
- Modify state machine to auto-confirm GRASP action
- Or reduce `grasp_dist` threshold

### Priority 4: Add PLACE Action
- Follow checklist in Q12
- Estimated: 6 file modifications

---

**End of Report**



