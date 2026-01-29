# Robotics Module - Virtual Arm Simulation

**PyBullet-based robotic arm simulation for intent-driven control**

---

## 📋 Overview

This module adds robotic arm simulation to the Intent Interface project, enabling:
- **Physical simulation** of a KUKA IIWA robot arm
- **Vision-to-action** pipeline (future weeks)
- **Safe, verifiable** robot control
- **Deterministic replay** and testing

### Week-by-Week Roadmap

| Week | Focus | Status |
|------|-------|--------|
| **Week 1** | Baseline sim + static arm | ✅ Complete |
| Week 2 | World model + action types | ✅ Complete |
| Week 3 | Gaze selection + target locking | ✅ Complete |
| Week 4 | State machine + orchestration | ✅ Complete |
| Week 5 | IK solver + autonomous execution | ✅ Complete |
| Week 6 | Grasping physics | ✅ Complete |
| Week 7 | Real BrainLink EEG integration | ✅ Complete |
| Week 8 | Safety monitor + recovery | ✅ Complete |
| **Week 9** | **Production demo infrastructure** | ✅ **Complete** |

---

## 🎯 Week 1: What's Included

### ✅ Core Features
- **Physics Simulation**: PyBullet engine with gravity, collisions
- **KUKA IIWA Robot**: 7-DOF arm with realistic joint limits
- **Scene Setup**: Table + manipulatable cube object
- **State Reading**: Joint angles, EE pose, object tracking
- **Visualization**: Interactive 3D GUI with camera controls

### 🚫 Week 1 Limitations (By Design)
- ❌ No movement (robot is static)
- ❌ No IK/FK yet
- ❌ No trajectories
- ❌ No grasping
- ❌ No intent integration

**Philosophy**: Build foundation first, add capabilities incrementally.

---

## 🚀 Quick Start

### Prerequisites

⚠️ **Python 3.12 required** (PyBullet not compatible with 3.13 yet)

```bash
# Option 1: Conda (recommended)
conda create -n intent-robotics python=3.12 -y
conda activate intent-robotics

# Option 2: pyenv
pyenv install 3.12.0
pyenv local 3.12.0
python -m venv .venv-robotics
source .venv-robotics/bin/activate
```

### Installation

```bash
# Install all dependencies (including PyBullet)
pip install -r requirements.txt

# Verify installation
python -c "import pybullet as p; print('✅ PyBullet:', p.getVersionInfo())"
```

### Run Demo

**Week 9 Unified Demo (Recommended)**:
```bash
# Happy path demo
python scripts/run_unified_arm_demo.py --mode happy_path

# Full walkthrough with EEG
python scripts/run_unified_arm_demo.py --mode full_narrative --eeg --eeg-source mock
```

**Legacy Demo (Week 1-8)**:
```bash
python scripts/run_virtual_arm_demo.py
```

**Expected Output:**
- 3D window opens showing robot arm, table, and red cube
- Real-time UI overlays showing system state
- Narrative descriptions of system behavior
- Trust metrics displayed (false_executions must be 0)
- Session logs saved to `logs/` directory

---

## 📁 Module Structure

```
src/robotics/
├── __init__.py           # Module exports
├── arm_state.py          # State data structures
│   ├── JointState        # Single joint state
│   ├── EndEffectorPose   # EE position + orientation
│   ├── ObjectPose        # Object tracking
│   └── ArmState          # Complete system state
│
├── arm_model.py          # Robot kinematic model
│   ├── JointInfo         # Joint specifications
│   └── ArmModel          # KUKA IIWA parameters
│
└── arm_simulator.py      # PyBullet integration
    └── ArmSimulator      # Main simulation engine

configs/
└── robotics.yaml         # All configurable parameters

scripts/
└── run_virtual_arm_demo.py  # Week 1 demo

tests/
└── test_week1_world_loads.py  # Comprehensive tests
```

---

## 🔧 Configuration

All parameters in `configs/robotics.yaml`:

```yaml
physics:
  time_step: 0.004166667  # 240 Hz
  gravity: [0, 0, -9.81]  # m/s²
  solver_iterations: 150
  sub_steps: 10

arm:
  model: "kuka_iiwa"
  base_position: [0, 0, 0]
  ee_link: "iiwa_link_ee"

scene:
  table:
    position: [0, 0, -0.025]
    size: [1.0, 1.0, 0.05]
  cube:
    position: [0.5, 0, 0.5]
    size: 0.05
    mass: 0.1
```

---

## 🧪 Testing

```bash
# Run all Week 1 tests
pytest tests/test_week1_world_loads.py -v

# Expected: 25+ tests passing
```

**Test Coverage:**
- ✅ World loading
- ✅ Robot structure (7 joints)
- ✅ State reading
- ✅ Physics simulation
- ✅ Collision detection
- ✅ Reset functionality
- ✅ Definition of Done validation

---

## 🎮 Usage Examples

### Basic Usage

```python
import yaml
from robotics import ArmSimulator

# Load config
with open('configs/robotics.yaml') as f:
    config = yaml.safe_load(f)

# Create simulator
with ArmSimulator(config, gui=True) as sim:
    # Get initial state
    state = sim.get_state()
    
    print(f"Joints: {state.num_joints}")
    print(f"EE Position: {state.end_effector.position}")
    
    # Step simulation (1 second)
    sim.step(240)
    
    # Get updated state
    state = sim.get_state()
    cube = state.get_object_by_name('cube')
    print(f"Cube fell to: {cube.position[2]:.3f}m")
```

### State Inspection

```python
# Read joint states
for joint in state.joints:
    print(f"{joint.name}: {joint.position:.3f} rad")
    print(f"  Limits: [{joint.position_min:.3f}, {joint.position_max:.3f}]")
    print(f"  Velocity: {joint.velocity:.3f} rad/s")

# Read end-effector pose
ee = state.end_effector
print(f"Position: {ee.position}")
print(f"Orientation (quat): {ee.orientation}")
print(f"Orientation (euler): {ee.euler_angles()}")

# Transform to 4x4 matrix
T = ee.to_matrix()
print(f"Transformation:\n{T}")
```

### Collision Detection

```python
state = sim.get_state()

if state.in_collision:
    print(f"⚠️  Collision detected!")
    print(f"Links involved: {state.collision_links}")
else:
    print("✅ No collisions")
```

### Serialization (Logging/Replay)

```python
import json

state = sim.get_state()

# Serialize to dict
state_dict = state.to_dict()

# Save to file
with open('arm_state.json', 'w') as f:
    json.dump(state_dict, f, indent=2)

# Contains: joints, EE pose, objects, collisions, timestamp
```

---

## 🤝 Integration with Intent Interface

**Week 1**: Robotics module is **independent**
- Runs standalone
- No connection to vision/intent pipeline yet

**Week 4+**: Will integrate via:
```python
# Vision detects object
object_pose = intent_interface.get_focused_object()

# Convert to robot workspace coordinate
target_pose = vision_to_robot_transform(object_pose)

# Robot reaches for object (Week 2+ IK)
trajectory = ik_solver.solve(target_pose)
sim.execute_trajectory(trajectory)
```

---

## 📊 KUKA IIWA Specifications

| Property | Value |
|----------|-------|
| **Model** | LBR iiwa 7 R800 |
| **DOF** | 7 (all revolute joints) |
| **Payload** | 7 kg |
| **Reach** | 800 mm |
| **Repeatability** | ±0.1 mm |
| **Joint Limits** | ±170° (typical) |
| **Max Velocity** | 85-135 °/s (varies by joint) |

### Joint Configuration

```
Joint 1: ±170° | 320 Nm | Base rotation
Joint 2: ±120° | 320 Nm | Shoulder pitch
Joint 3: ±170° | 176 Nm | Elbow rotation
Joint 4: ±120° | 176 Nm | Elbow pitch
Joint 5: ±170° | 110 Nm | Wrist rotation
Joint 6: ±120° |  40 Nm | Wrist pitch
Joint 7: ±175° |  40 Nm | Flange rotation
```

---

## 🐛 Troubleshooting

### PyBullet Not Found

```
ModuleNotFoundError: No module named 'pybullet'
```

**Solution**: Use Python 3.12 (not 3.13)

```bash
conda create -n intent-robotics python=3.12
conda activate intent-robotics
pip install -r requirements.txt
```

### GUI Window Not Showing

**Linux**:
```bash
sudo apt-get install libglfw3 libglfw3-dev
export DISPLAY=:0
```

**macOS**: Should work natively

**Windows**: Should work natively

### Simulation Runs Too Fast/Slow

Adjust time step in `configs/robotics.yaml`:
```yaml
physics:
  time_step: 0.008  # Slower (120 Hz)
  # or
  time_step: 0.002  # Faster (500 Hz)
```

### Robot/Cube Falls Through Table

Check table position and size:
```yaml
scene:
  table:
    position: [0, 0, -0.025]  # Ensure z is correct
    size: [1.0, 1.0, 0.05]     # Ensure thickness > 0
```

---

## 📖 API Reference

### `ArmSimulator`

**Constructor**:
```python
ArmSimulator(config: dict, gui: bool = True)
```

**Methods**:
- `get_state() -> ArmState`: Read current state
- `step(num_steps: int = 1)`: Advance simulation
- `reset()`: Reset to initial conditions
- `close()`: Cleanup and shutdown

**Properties**:
- `arm_model: ArmModel`: Robot kinematic model
- `robot_id: int`: PyBullet body ID
- `step_count: int`: Simulation steps elapsed
- `time_step: float`: Physics timestep (seconds)

### `ArmState`

**Properties**:
- `joints: List[JointState]`: All joint states
- `end_effector: EndEffectorPose`: EE pose
- `objects: List[ObjectPose]`: Scene objects
- `timestamp: float`: Simulation time
- `in_collision: bool`: Collision status

**Methods**:
- `get_joint_by_name(name) -> JointState`
- `get_object_by_name(name) -> ObjectPose`
- `is_valid() -> bool`: Check all joints within limits
- `to_dict() -> dict`: Serialize to JSON-compatible dict

### `ArmModel`

**Properties**:
- `name: str`: Robot model name
- `num_joints: int`: Number of joints (7)
- `joints: List[JointInfo]`: Joint specifications

**Methods**:
- `get_joint_info(index) -> JointInfo`
- `get_joint_by_name(name) -> JointInfo`
- `is_position_valid(positions) -> (bool, str)`
- `clamp_positions(positions) -> np.ndarray`
- `get_joint_limits() -> (lower, upper)`

---

## Week 9: Production Demo Infrastructure ✅

**Goal**: Unified demo system with comprehensive metrics and transparency.

**Features**:
- ✅ UI Snapshot architecture (single source of truth)
- ✅ Structured event logging (JSONL for replay)
- ✅ Narrative logger (human-readable event stream)
- ✅ Metrics collector (comprehensive performance tracking)
- ✅ Demo modes (happy_path, safety_refusal, recovery, full_narrative)
- ✅ Unified demo runner (one command for all modes)
- ✅ Metrics report generator (markdown + JSON export)
- ✅ 5-minute demo script (complete walkthrough)

### Key Components

**UI Snapshot - Complete System State**:
```python
@dataclass
class ArmUISnapshot:
    state: str
    locked_object_id: int
    proposed_action: str
    eeg_stable: bool
    paused: bool
    false_executions: int  # MUST BE 0
    # ... 30+ fields capturing complete system state
```

**Event Logger - Structured JSONL**:
```python
logger.emit(EventType.EXECUTION_STARTED, {"action": "reach_forward"})
logger.emit(EventType.PAUSE_TRIGGERED, {"trigger": "eeg_unstable"})
# All events logged with timestamp and session_id
```

**Narrative Logger - Human-Readable**:
```python
lines = narrator.describe(snapshot)
# Output:
# ["✓ Locked onto object 3", 
#  "💡 Proposed: Move Arm Up — EE too low",
#  "⚠️  PAUSED: EEG signal unstable"]
```

**Metrics Collector - Comprehensive Tracking**:
```python
metrics.update(snapshot, dt)
metrics.save_json("session_metrics.json")
# Tracks: false_executions, pauses, FPS, EEG quality, trust metrics
```

### Running Demos

```bash
# Happy path (normal operation)
python scripts/run_unified_arm_demo.py --mode happy_path

# Safety demonstration (blocking unsafe actions)
python scripts/run_unified_arm_demo.py --mode safety_refusal --eeg --eeg-source mock

# Recovery workflow (pause → recover)
python scripts/run_unified_arm_demo.py --mode recovery --eeg --eeg-source mock --faults

# Full 5-minute walkthrough
python scripts/run_unified_arm_demo.py --mode full_narrative --eeg --eeg-source mock

# Generate metrics report
python scripts/generate_arm_metrics_report.py --latest --format markdown,console
```

### Demo Modes

1. **happy_path**: Normal operation end-to-end (gaze → confirm → execute → grasp)
2. **safety_refusal**: High variance blocks confirmation (demonstrates decision strategy)
3. **recovery**: EEG dropout → pause → recover (demonstrates robustness)
4. **full_narrative**: Complete 5-minute scripted walkthrough

### Transparency Features

- **Every state change narrated** - Real-time human-readable explanations
- **All decisions logged** - JSONL format for deterministic replay
- **Complete UI snapshot every frame** - Single source of truth
- **Trust metrics always visible** - false_executions, pauses, safety events
- **Event replay capability** - Analyze sessions after the fact

### Week 9 Module Structure

```
src/intent_core/
├── arm_ui_snapshot.py       # Complete system state (30+ fields)
├── arm_event_logger.py       # JSONL structured logging
├── arm_narrative_logger.py   # Human-readable narration
└── arm_metrics_collector.py  # Performance & trust metrics

src/sim/
├── demo_modes.py             # Pre-configured scenarios
└── fault_injection.py        # Deterministic testing (Week 8)

scripts/
├── run_unified_arm_demo.py         # Main demo runner (Week 9)
├── generate_arm_metrics_report.py  # Metrics analysis
└── run_virtual_arm_demo.py         # Legacy demo (deprecated)

docs/
└── arm_demo_script_5min.md   # Complete presentation script

tests/
└── test_week9_final_trust_regressions.py  # 8 comprehensive tests
```

### Testing

```bash
# Run Week 9 trust regression tests
pytest tests/test_week9_final_trust_regressions.py -v
# Expected: 8 passed

# Run all robotics tests (Week 1-9)
pytest tests/test_week*.py -v
# Expected: 31+ passed
```

**Week 9 Tests**:
- ✅ `false_executions == 0` across all demo modes
- ✅ Snapshot consistency (frame count, timestamps)
- ✅ Event logging integrity (valid JSONL)
- ✅ Metrics collection & export
- ✅ Deterministic scripted scenarios
- ✅ Pause clears confirmation
- ✅ Recovery mode with fault injection
- ✅ Safety refusal with blocked confirmations

### Documentation

- **[5-Minute Demo Script](../docs/arm_demo_script_5min.md)** - Complete walkthrough with narration
- **Unified Demo Runner** - `--help` for all options
- **Metrics Reports** - JSON and Markdown export
- **Deprecation Notices** - Legacy scripts clearly marked

### Week 9 Definition of Done

All verified by tests:

- [x] UI snapshot architecture implemented
- [x] Event logging (JSONL) working
- [x] Narrative logger generating descriptions
- [x] Metrics collector tracking all metrics
- [x] 4 demo modes configured
- [x] Unified demo runner created
- [x] Metrics report generator working
- [x] 5-minute demo script complete
- [x] All tests passing (8/8)
- [x] Legacy demo script deprecated
- [x] Complete documentation
- [x] **`false_executions == 0`** (always)

**Status: Week 9 COMPLETE** ✅

---

## 🔮 Future Enhancements

### Potential Extensions
- **Advanced EEG Integration**: Multi-channel analysis, P300 detection
- **Vision Integration**: Camera-based object detection → robot workspace
- **Obstacle Avoidance**: Dynamic replanning with moving obstacles
- **Multi-Arm Coordination**: Coordinated dual-arm manipulation
- **Force Control**: Compliant grasping with force/torque sensors
- **Real Hardware**: Deploy to physical KUKA IIWA robot
- **VR/AR Interface**: Immersive control and monitoring

---

## 📚 References

- [PyBullet Documentation](https://pybullet.org/)
- [KUKA IIWA Datasheet](https://www.kuka.com/en-us/products/robotics-systems/industrial-robots/lbr-iiwa)
- [Intent Interface Paper](https://intentinterface.ai) *(if published)*

---

## ✅ Definition of Done

### Week 1 (Baseline)
All checkboxes verified by `test_week1_world_loads.py`:

- [x] World loads without crashes
- [x] Robot visible in GUI
- [x] Table and cube present
- [x] Physics working (gravity affects cube)
- [x] Can read joint angles (7 joints)
- [x] Can read EE pose (position + orientation)
- [x] Can read object pose
- [x] Robot doesn't move (Week 1 constraint)
- [x] Clean module architecture
- [x] Configuration-driven
- [x] All tests passing

**Status: Week 1 COMPLETE** ✅

### Week 9 (Production Demo)
All checkboxes verified by `test_week9_final_trust_regressions.py`:

- [x] UI snapshot architecture
- [x] Event logging (JSONL)
- [x] Narrative logger
- [x] Metrics collector
- [x] 4 demo modes
- [x] Unified demo runner
- [x] Report generator
- [x] 5-minute demo script
- [x] **`false_executions == 0`** across all modes
- [x] 8/8 tests passing

**Status: Week 9 COMPLETE** ✅

---

## 🙋 FAQ

**Q: Why KUKA IIWA specifically?**  
A: 7-DOF arm (redundancy), collaborative robot (safe), widely used in research, good PyBullet URDF available.

**Q: Can I use a different robot?**  
A: Yes! Modify `arm_model.py` and provide a new URDF. Interface is generic.

**Q: What's the difference between `run_virtual_arm_demo.py` and `run_unified_arm_demo.py`?**  
A: `run_unified_arm_demo.py` (Week 9) is the production demo runner with full logging, metrics, and demo modes. `run_virtual_arm_demo.py` is the legacy script, maintained for backward compatibility.

**Q: How do I prove the system is safe?**  
A: Run the metrics report: `python scripts/generate_arm_metrics_report.py --latest`. Look for `false_executions == 0`.

**Q: Can I run headless (no GUI)?**  
A: Yes: `ArmSimulator(config, gui=False)`

**Q: Is this deterministic?**  
A: Yes (given same initial state + control inputs). PyBullet and fault injection are both deterministic with seeded RNGs.

**Q: Can I replay a session?**  
A: Yes! All events are logged to JSONL. Use the event logs for analysis and replay.

**Q: Which demo mode should I use for a presentation?**  
A: `--mode full_narrative` gives a complete 5-minute walkthrough. See `docs/arm_demo_script_5min.md` for the presentation script.

---

**Next**: See `docs/ROBOTICS_SETUP.md` for environment setup  
**Questions**: Open an issue or see main README

