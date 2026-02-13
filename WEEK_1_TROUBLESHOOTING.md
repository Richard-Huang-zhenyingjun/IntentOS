# Week 1 Robotics: Troubleshooting Guide 🔧

Common issues and solutions for Week 1 robotics implementation.

---

## 🐛 Installation Issues

### Issue: `ModuleNotFoundError: No module named 'pybullet'`

**Symptoms:**
```
Traceback (most recent call last):
  File "scripts/run_virtual_arm_demo.py", line 18, in <module>
    import pybullet as p
ModuleNotFoundError: No module named 'pybullet'
```

**Solution:**
```bash
# Recommended: Install via conda (has prebuilt binaries)
conda install -c conda-forge pybullet -y

# Alternative: Install via pip
pip install "pybullet>=3.2.5"
```

**Verification:**
```bash
python -c "import pybullet; print('✅ PyBullet installed')"
```

---

### Issue: `ModuleNotFoundError: No module named 'scipy'`

**Solution:**
```bash
pip install "scipy>=1.11.0"
```

**Verification:**
```bash
python -c "import scipy; print('✅ scipy installed')"
```

---

### Issue: `ModuleNotFoundError: No module named 'yaml'`

**Solution:**
```bash
pip install "pyyaml>=6.0"
```

---

## 📁 File and Path Issues

### Issue: `FileNotFoundError: configs/robotics.yaml`

**Symptoms:**
```
FileNotFoundError: [Errno 2] No such file or directory: 'configs/robotics.yaml'
```

**Cause:** Running script from wrong directory (e.g., inside `scripts/` folder)

**Solution:**
```bash
# Make sure you're in the project root
cd /Users/richardhuang/Intent\ Interface\ Prototype

# Verify you can see configs/ directory
ls configs/robotics.yaml

# Now run the script
python scripts/run_virtual_arm_demo_headless.py
```

**Quick Check:**
```bash
# You should see configs/, scripts/, src/, tests/
ls -d */ | head -5
```

---

### Issue: `Failed to load URDF: kuka_iiwa/model.urdf`

**Symptoms:**
```
Error: Failed to load robot URDF from kuka_iiwa/model.urdf
```

**Cause:** PyBullet can't find built-in URDF files

**Solution:** This is handled automatically in `arm_model.py`:
```python
import pybullet_data
p.setAdditionalSearchPath(pybullet_data.getDataPath())
```

**If still failing:**
```bash
# Verify pybullet_data is available
python -c "import pybullet_data; print(pybullet_data.getDataPath())"

# Should print something like:
# /opt/anaconda3/lib/python3.13/site-packages/pybullet_data
```

**Manual Fix (if needed):**
- Reinstall PyBullet: `conda install -c conda-forge pybullet -y`
- Check that `pybullet_data` is in the same environment

---

## 🖥️ GUI and Display Issues

### Issue: `gladLoaderLoadGL failed!` (macOS)

**Symptoms:**
```
gladLoaderLoadGL failed!
2026-01-07 16:29:07.183 python[68945:27881664] Connection Invalid error
```

**Cause:** macOS OpenGL initialization issue in Cursor terminal

**Solution:** Use headless mode (recommended):
```bash
python scripts/run_virtual_arm_demo_headless.py
```

**Alternative:** Run from native terminal:
```bash
# Open Terminal.app or iTerm
cd "/Users/richardhuang/Intent Interface Prototype "
python scripts/run_virtual_arm_demo.py
```

**Why it's not a problem:**
- ✅ All functionality validated via headless mode
- ✅ All 7 tests pass
- ✅ Physics simulation works perfectly

---

### Issue: GUI window is tiny or camera is wrong

**Symptoms:**
- PyBullet window opens but view is zoomed way in/out
- Can't see robot or table
- Camera angle is awkward

**Solution:** Adjust camera settings in `configs/robotics.yaml`:

```yaml
scene:
  use_gui: true
  camera:
    distance: 1.5    # Distance from target (increase to zoom out)
    yaw: 50          # Horizontal rotation (degrees)
    pitch: -35       # Vertical angle (negative = looking down)
    target: [0.3, 0, 0.2]  # Point camera looks at
```

**Quick adjustments:**
- **Too close:** Increase `distance` to 2.0 or 2.5
- **Wrong angle:** Try `yaw: 45, pitch: -30`
- **Off-center:** Adjust `target` to center of scene

**Interactive adjustment:**
In PyBullet GUI (if working):
- Right-click drag: Rotate camera
- Scroll wheel: Zoom in/out
- Ctrl+drag: Pan camera

---

## 🎮 Physics Issues

### Issue: Cube falls through table

**Symptoms:**
- Cube starts on table but falls through and hits ground
- Object Z position ends up at ~0.02m instead of 0.62m

**Likely Causes:**
1. Table height incorrect
2. Object start position too high/low
3. Collision disabled

**Solution:**

**Check 1: Table configuration**
```yaml
table:
  height: 0.6              # Surface at 60cm
  dimensions: [0.8, 1.2, 0.05]
  position: [0, 0, 0.575]  # height/2 below surface (0.6 - 0.025)
```

**Check 2: Object start pose**
```yaml
object:
  size: 0.04               # 4cm cube (radius = 0.02m)
  start_pose:
    position: [0.3, 0.0, 0.65]  # Slightly above table
```

**Expected behavior:**
- Initial: Object at 0.65m (5cm above table surface)
- After physics: Object settles to 0.62m (table + radius)
- Settling distance: ~3cm

**Verification:**
```bash
python scripts/run_virtual_arm_demo_headless.py
# Look for: "Actual object height: 0.620m"
```

---

### Issue: Object flies away or explodes

**Symptoms:**
- Cube shoots off into space
- Physics simulation unstable
- Objects vibrating or jittering

**Cause:** Timestep too large or solver iterations too low

**Solution:** Check physics settings in `configs/robotics.yaml`:
```yaml
physics:
  timestep: 0.008333          # 120 Hz (smaller = more stable)
  gravity: [0, 0, -9.81]
  num_solver_iterations: 50   # Higher = more accurate
```

**For more stability:**
```yaml
physics:
  timestep: 0.004167          # 240 Hz (even more stable)
  num_solver_iterations: 100  # More solver iterations
```

---

## 🤖 Robot Issues

### Issue: Robot not visible in scene

**Symptoms:**
- Can see table and cube but no robot arm
- Tests pass but demo shows nothing

**Likely Cause:** Robot base position incorrect

**Solution:** Check robot configuration:
```yaml
robot:
  use_builtin: true
  model_name: "kuka_iiwa/model.urdf"
  base_pose:
    position: [0, 0, 0.6]      # ON table surface (z = table height)
    orientation: [0, 0, 0, 1]
```

**Common mistakes:**
- ❌ `position: [0, 0, 0]` - Robot on ground (hidden by table)
- ❌ `position: [0, 0, 2.0]` - Robot floating way above
- ✅ `position: [0, 0, 0.6]` - Robot base on table surface

**Verification:**
```python
# In headless demo, check EE position
# End effector position: [0. 0. 1.861]
# This is ~1.26m above base (0.6 + 1.26 = 1.861) ✓
```

---

### Issue: Robot has wrong number of joints

**Symptoms:**
```
AssertionError: Joint count mismatch
Expected: 7, Got: 14
```

**Cause:** Counting all links including fixed joints

**Solution:** This is handled in `arm_model.py`:
```python
# Only count REVOLUTE and PRISMATIC joints (controllable)
joint_type = p.getJointInfo(body_id, i)[2]
if joint_type in [p.JOINT_REVOLUTE, p.JOINT_PRISMATIC]:
    joint_indices.append(i)
```

**No action needed** - this filtering is automatic.

---

### Issue: End effector name not found

**Symptoms:**
```
ValueError: End effector link 'lbr_iiwa_link_7' not found
```

**Cause:** Wrong EE link name for robot model

**Solution:** Check available links:
```python
# In Python console:
import pybullet as p
import pybullet_data

p.connect(p.DIRECT)
p.setAdditionalSearchPath(pybullet_data.getDataPath())
robot = p.loadURDF("kuka_iiwa/model.urdf")

# Print all link names
for i in range(p.getNumJoints(robot)):
    info = p.getJointInfo(robot, i)
    print(f"Link {i}: {info[12].decode('utf-8')}")
```

**For KUKA iiwa:**
- ✅ Correct: `"lbr_iiwa_link_7"` (last link)
- Common alternatives: `"tool0"`, `"ee_link"`, etc.

---

## 🧪 Test Issues

### Issue: Tests fail with "Simulator not connected"

**Solution:** Make sure fixture is properly setting up/tearing down:
```python
@pytest.fixture
def simulator():
    sim = ArmSimulator(cfg_path='configs/robotics_test.yaml')
    sim.connect()
    sim.reset_world()
    
    yield sim  # Important: use yield, not return
    
    sim.close()  # Cleanup happens after test
```

---

### Issue: Test fails on physics stepping with tolerance error

**Symptoms:**
```
AssertionError: Object should settle at 0.62m
assert np.float64(0.030013183729741266) < 0.01
```

**Cause:** Object settles differently than expected

**Solution:** Check tolerance is appropriate:
```python
# Allow 1cm tolerance for physics settling
expected_z = 0.62  # table + radius
assert abs(z_after - expected_z) < 0.01, f"Expected {expected_z}m"
```

**If object settles to different height:**
1. Verify table height: 0.6m
2. Verify cube size: 0.04m (radius = 0.02m)
3. Expected: 0.6 + 0.02 = 0.62m

---

## 🚀 Performance Issues

### Issue: Simulation running too slow

**Solution 1:** Disable GUI
```bash
python scripts/run_virtual_arm_demo_headless.py  # Much faster
```

**Solution 2:** Reduce physics accuracy (if acceptable)
```yaml
physics:
  timestep: 0.016667        # 60 Hz instead of 120 Hz
  num_solver_iterations: 25  # Fewer iterations
```

**Solution 3:** Use DIRECT mode in code:
```python
# In your script
cfg['scene']['use_gui'] = False
```

---

### Issue: Tests taking too long

**Current performance:** 7 tests in ~0.30s (this is good!)

**If slower:**
- Make sure using DIRECT mode (no GUI)
- Check if other PyBullet processes running
- Close unnecessary applications

---

## 📋 Verification Checklist

Use this to systematically check your setup:

### Environment
- [ ] Python 3.8+ installed
- [ ] PyBullet installed: `python -c "import pybullet"`
- [ ] scipy installed: `python -c "import scipy"`
- [ ] pyyaml installed: `python -c "import yaml"`

### Files Present
- [ ] `configs/robotics.yaml` exists
- [ ] `src/robotics/__init__.py` exists
- [ ] `src/robotics/arm_model.py` exists
- [ ] `src/robotics/arm_state.py` exists
- [ ] `src/robotics/arm_simulator.py` exists
- [ ] `scripts/run_virtual_arm_demo_headless.py` exists
- [ ] `tests/test_week1_world_loads.py` exists

### Quick Tests
- [ ] Run: `pytest tests/test_week1_world_loads.py -v`
- [ ] Expected: `7 passed in ~0.3s`
- [ ] Run: `python scripts/run_virtual_arm_demo_headless.py`
- [ ] Expected: "Physics working correctly - object stable on table!"

---

## 🆘 Still Having Issues?

### Debug Mode

Add debug prints to see what's happening:

```python
# In your script
import pybullet as p

# After connecting
print(f"PyBullet version: {p.getVersionInfo()}")
print(f"Physics client: {sim.physics_client}")

# After loading robot
print(f"Robot ID: {sim.robot.body_id}")
print(f"Number of joints: {sim.robot.num_joints}")
print(f"Joint names: {sim.robot.joint_names}")

# After physics step
pos, _ = sim.get_object_pose()
print(f"Object position: {pos}")
```

### Minimal Test

Create a minimal test script:

```python
import pybullet as p
import pybullet_data

# Connect
client = p.connect(p.DIRECT)
print(f"✅ Connected: {client}")

# Load URDF
p.setAdditionalSearchPath(pybullet_data.getDataPath())
robot = p.loadURDF("kuka_iiwa/model.urdf")
print(f"✅ Robot loaded: {robot}")

# Check joints
n_joints = p.getNumJoints(robot)
print(f"✅ Number of joints: {n_joints}")

p.disconnect()
print("✅ Test complete")
```

---

## 📚 Additional Resources

- **PyBullet Quickstart:** https://pybullet.org/wordpress/
- **URDF Format:** http://wiki.ros.org/urdf
- **Our Documentation:**
  - `WEEK_1_COMPLETE.md` - Full completion report
  - `WEEK_1_QUICK_START.md` - Quick start guide
  - `WEEK_1_ROBOTICS_VALIDATION.md` - Validation details

---

## ✅ Success Criteria

Your Week 1 setup is working correctly if:

1. ✅ Tests pass: `pytest tests/test_week1_world_loads.py -v` → 7 passed
2. ✅ Headless demo works: Shows physics validation with 0.0mm error
3. ✅ No Python exceptions during execution
4. ✅ Object settles to ~0.62m (table height + cube radius)
5. ✅ Robot has 7 controllable joints
6. ✅ End effector position is readable (~1.86m in Z)

**If all checked:** Your Week 1 is complete! 🎉

---

**Last Updated:** January 7, 2026  
**Platform:** macOS 24.6.0, Python 3.13, PyBullet 3.25






