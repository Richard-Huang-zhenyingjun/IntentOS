# Week 0 Motion Baseline Report
Date: February 2, 2026

## Objective
Verify arm physically moves in PyBullet with deterministic commands.

## Results Summary
- ✅ Motion baseline script: PASS
- ✅ Joint discovery: 7 revolute joints found
- ✅ Controller semantics: Fixed multi-frame pattern
- ✅ Headless test: PASS
- ✅ Demo execution: Arm moves on confirm

## Joint Discovery Results
```
Discovered joints: [0, 1, 2, 3, 4, 5, 6]
End effector link index: 6
Joint 0 name: lbr_iiwa_joint_1
```

## Controller Parameters (Validated)
```yaml
max_force: 400.0
position_gain: 0.2
velocity_gain: 1.0
tolerance_rad: 0.02
settle_frames_required: 10
```

## Known Safe Targets
- Joint 0: Can reach ±0.5 rad from neutral
- Cartesian upward: +0.1m from current position

## Bugs Fixed
1. Missing `forces` parameter in motor control
2. Controller returning `True` on failure paths
3. Orchestrator checking completion in same frame as start
4. Hardcoded joint indices (now discovered)
5. GUI connection crash on macOS (fallback to DIRECT mode)

## Implementation Details

### Day 1: Startup Environment
- Added diagnostic banner (`src/core/diag.py`)
- Added debug configuration to `configs/default.yaml`
- Verified execution paths and Python environment

### Day 2: Joint Discovery
- Created `src/robot/joint_discovery.py` module
- Integrated discovery into `RobotSimulator`
- Added `get_joint_indices()` and `get_ee_link_index()` methods
- Joint table printing for diagnostics

### Day 3: Motion Baseline Script
- Created `scripts/run_motion_baseline.py`
- Tests PyBullet + URDF + motor control in isolation
- Validates joint movement (0.5 rad target, >0.1 rad movement required)
- Fixed macOS GUI crash with DIRECT mode fallback

### Day 4: Controller Semantics
- Added motor control parameters from config
- Fixed `move_to_position()` to compute IK immediately
- Fixed `update()` return semantics (True = complete, False = executing/failed)
- Implemented settle logic with frame counter
- Added configurable diagnostic logging

### Day 5: Orchestrator Multi-Frame Pattern
- Fixed `_execute_move_up()` to use multi-frame pattern
- Fixed `_execute_reach()` to use multi-frame pattern
- Fixed `_execute_place()` to use multi-frame pattern
- Pattern: Start motion → return immediately → check completion in subsequent frames

### Day 6: Headless Test
- Created `tests/test_arm_moves_basic.py`
- Pytest-compatible test for CI/CD
- Validates basic joint movement without GUI

## Test Results

### Motion Baseline Script
```
[BASELINE] Loaded robot from: kuka_iiwa/model.urdf
[BASELINE] Discovered 7 revolute joints: [0, 1, 2, 3, 4, 5, 6]
[BASELINE] Final position: 0.5000
[BASELINE] Total movement: 0.5000 rad
[BASELINE] ✅ SUCCESS - Joint moved significantly!
```

### Controller Initialization
```
[CTRL] Initialized with 7 joints
[CTRL] max_force=400.0, tolerance=0.02
```

### Joint Discovery Output
```
================================================================================
JOINT TABLE
================================================================================
Index  Name                 Type         Lower    Upper   
--------------------------------------------------------------------------------
0      lbr_iiwa_joint_1    REVOLUTE     -2.96    2.96    
1      lbr_iiwa_joint_2    REVOLUTE     -2.09    2.09    
2      lbr_iiwa_joint_3    REVOLUTE     -2.96    2.96    
3      lbr_iiwa_joint_4    REVOLUTE     -2.09    2.09    
4      lbr_iiwa_joint_5    REVOLUTE     -2.96    2.96    
5      lbr_iiwa_joint_6    REVOLUTE     -2.09    2.09    
6      lbr_iiwa_joint_7    REVOLUTE     -2.96    2.96    
7      base_joint          FIXED        0.00     -1.00   
================================================================================
```

## Remaining Limitations
- IK convergence not validated for all workspace regions
- Collision detection not tested
- Grasp constraint not verified
- No validation of joint limits during motion
- Settle logic may be too strict for slow motions

## Files Created/Modified

### New Files
- `src/core/diag.py` - Diagnostic utilities
- `src/robot/joint_discovery.py` - Joint discovery module
- `scripts/run_motion_baseline.py` - Motion baseline test script
- `tests/test_arm_moves_basic.py` - Pytest test for arm movement
- `docs/week0_motion_baseline_report.md` - This report

### Modified Files
- `configs/default.yaml` - Added debug and robot parameters
- `src/robot/simulator.py` - Integrated joint discovery
- `src/robot/controller.py` - Fixed semantics and multi-frame pattern
- `scripts/run_demo.py` - Added startup banner
- `src/core/orchestrator.py` - Fixed execution methods

## Next Steps (Week 1)
- Create messy table environment
- Build heuristic proposer for CLEAN_TABLE
- Implement plan compiler (proposal → primitives)
- Add collision avoidance
- Validate IK for full workspace
- Test grasp/place sequences

## Lessons Learned
1. **Multi-frame pattern is critical**: Motion must start in one frame and complete check in subsequent frames
2. **Force parameter is required**: PyBullet motors need explicit `forces` parameter to move
3. **Joint discovery is essential**: Hardcoded indices break with different URDFs
4. **Settle logic prevents premature completion**: Multiple frames below threshold ensures stable completion
5. **macOS GUI issues**: DIRECT mode is more reliable for automated testing

## Success Criteria Met
✅ Arm physically moves when commanded  
✅ Joint discovery works with KUKA IIWA  
✅ Controller properly manages multi-frame execution  
✅ Orchestrator correctly coordinates motion  
✅ Tests validate basic functionality  

**Week 0 Status: COMPLETE** ✅



