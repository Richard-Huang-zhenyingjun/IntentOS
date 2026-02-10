# Week 1 Robotics: Quick Start Guide 🚀

**Ready to validate Week 1 robotics implementation in under 1 minute!**

---

## ⚡ 30-Second Validation

```bash
# 1. Run automated tests (fastest way to validate)
pytest tests/test_week1_world_loads.py -v

# Expected: 7 passed in ~0.3s ✅
```

---

## 🎬 See It In Action (2 minutes)

```bash
# 2. Run headless demo (works on all platforms)
python scripts/run_virtual_arm_demo_headless.py
```

**What you'll see:**
- ✓ World loading messages
- ✓ Initial state: Robot at [0, 0, 1.861]m, Cube at [0.3, 0, 0.65]m
- ✓ Physics simulation: 100 steps
- ✓ Final state: Cube settled to [0.3, 0, 0.62]m (perfect!)
- ✓ Validation: 0.0mm error from expected height

---

## 🖥️ GUI Demo (Optional)

```bash
# 3. Try GUI demo (may have issues on macOS)
python scripts/run_virtual_arm_demo.py
```

**If GUI works:**
- You'll see PyBullet window with 3D scene
- Ground plane + brown table + red cube + KUKA robot
- Interactive controls: ESC/Q=quit, SPACE=pause, R=reset

**If GUI fails (macOS OpenGL issue):**
- Don't worry! Core functionality is validated via:
  - ✅ All 7 tests passing
  - ✅ Headless demo working
  - ✅ Physics simulation correct

---

## ✅ Success Checklist

After running the commands above, verify:

- [ ] All 7 tests passed (green checkmarks)
- [ ] Headless demo completed without errors
- [ ] Cube settled to 0.62m (table height + radius)
- [ ] Physics validation shows 0.0mm error
- [ ] No Python exceptions or crashes

**If all checked:** Week 1 is complete! 🎉

---

## 📊 What's Being Validated?

### Tests Validate:
1. **Connection** - PyBullet initializes correctly
2. **World Loading** - Plane, table, cube, robot all present
3. **Robot Metadata** - 7 joints, valid limits, EE link
4. **State Reading** - Joints, velocities, EE pose readable
5. **Object Pose** - Position and orientation tracked
6. **Physics** - Gravity and collisions work correctly
7. **Joint Limits** - Initial config within bounds

### Demo Shows:
- World creation from config
- Physics simulation over time
- State inspection (before/after)
- Automatic validation of physics accuracy

---

## 🐛 Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'pybullet'"
**Fix:**
```bash
conda install -c conda-forge pybullet -y
```

### Issue: GUI demo shows OpenGL error
**Fix:** This is expected on macOS. Use headless demo instead:
```bash
python scripts/run_virtual_arm_demo_headless.py
```

### Issue: Tests fail on physics stepping
**Check:** Make sure cube settles to ~0.62m (tolerance: ±1cm)
- This is table height (0.6m) + cube radius (0.02m)

---

## 📁 Project Structure

```
Intent Interface Prototype/
├── configs/
│   └── robotics.yaml                   # Scene and physics config
├── src/
│   └── robotics/
│       ├── __init__.py                 # Module exports
│       ├── arm_model.py                # URDF loader
│       ├── arm_state.py                # State reader
│       └── arm_simulator.py            # Main simulator
├── scripts/
│   ├── run_virtual_arm_demo.py         # GUI version
│   └── run_virtual_arm_demo_headless.py # Headless version
└── tests/
    └── test_week1_world_loads.py       # Validation tests
```

---

## 🎯 Next Steps

After validating Week 1:

1. **Week 2:** Inverse kinematics and motion planning
2. **Week 3:** Trajectory execution
3. **Week 4:** Grasp planning
4. **Week 5:** Vision-robotics integration

---

## 💡 Pro Tips

### Fast Development Loop
```bash
# Run tests on every change
pytest tests/test_week1_world_loads.py -v --tb=short

# Quick state check
python scripts/run_virtual_arm_demo_headless.py
```

### Debugging
```python
# In your code, print intermediate states
from robotics import read_arm_state
state = read_arm_state(robot)
print(f"EE position: {state.ee_pos}")
```

### Configuration
Edit `configs/robotics.yaml` to change:
- Physics timestep and gravity
- Camera position
- Object size, mass, position
- Table dimensions

---

## 📚 Documentation

- **Full Validation Report:** `WEEK_1_ROBOTICS_VALIDATION.md`
- **Implementation Details:** See docstrings in `src/robotics/*.py`
- **Test Details:** `tests/test_week1_world_loads.py`

---

**Status:** ✅ Week 1 Complete and Validated  
**Time to Validate:** < 1 minute  
**Confidence Level:** 100% (all tests passing)





