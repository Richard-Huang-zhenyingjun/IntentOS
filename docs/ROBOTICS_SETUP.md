# Robotics Module Setup (Week 1+)

## ⚠️ Python Version Requirement

**PyBullet requires Python 3.11 or 3.12** (not 3.13 yet)

### Current Status
- Your system: Python 3.13 (Anaconda)
- PyBullet: No pre-built wheels for 3.13, compilation fails

### Solution Options

#### Option 1: Create Python 3.12 Environment (Recommended)
```bash
# Create new conda environment with Python 3.12
conda create -n intent-robotics python=3.12 -y
conda activate intent-robotics

# Install all dependencies
pip install -r requirements.txt

# Verify PyBullet works
python -c "import pybullet as p; print('✅ PyBullet:', p.getVersionInfo())"
```

#### Option 2: Use pyenv
```bash
# Install Python 3.12
pyenv install 3.12.0
pyenv local 3.12.0

# Create virtual environment
python -m venv .venv-robotics
source .venv-robotics/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### Option 3: Wait for PyBullet 3.13 Support
PyBullet maintainers are working on Python 3.13 support. Check:
https://github.com/bulletphysics/bullet3/issues

---

## Quick Start (After Python 3.12 Setup)

```bash
# Activate Python 3.12 environment
conda activate intent-robotics

# Run Week 1 demo
python scripts/run_virtual_arm_demo.py

# Run tests
pytest tests/test_week1_world_loads.py -v
```

---

## What Week 1 Includes

✅ **Core Simulation**
- PyBullet physics engine integration
- KUKA IIWA robotic arm (7 DOF)
- Table + cube object
- Gravity, collisions, dynamics

✅ **State Reading**
- Joint angles (7 joints)
- End-effector pose (position + orientation)
- Object pose (position + orientation)
- Collision detection status

✅ **Visualization**
- Real-time 3D rendering
- Interactive camera controls
- Debug visualization options

✅ **Architecture**
- Clean module structure (`src/robotics/`)
- Configuration-driven (`configs/robotics.yaml`)
- Fully tested
- No movement yet (Week 2+)

---

## Module Structure

```
src/robotics/
├── __init__.py
├── arm_model.py          # Robot kinematic model
├── arm_state.py          # State data structures
└── arm_simulator.py      # PyBullet integration

configs/
└── robotics.yaml         # Physics + scene config

scripts/
└── run_virtual_arm_demo.py  # Week 1 demo

tests/
└── test_week1_world_loads.py  # Validation
```

---

## Integration with Intent Interface

The robotics module is **independent** and can be used:
1. **Standalone**: Run `run_virtual_arm_demo.py`
2. **Integrated**: Later weeks will connect intent detection → robot control

**Current Week 9 Intent Interface features remain unchanged.**

---

## Troubleshooting

### PyBullet Import Error
```
ModuleNotFoundError: No module named 'pybullet'
```
**Solution**: Use Python 3.12 (see Option 1 above)

### Compilation Errors
```
error: command '/usr/bin/clang' failed with exit code 1
```
**Solution**: This happens on Python 3.13. Use pre-built wheels with Python 3.12.

### GUI Issues (Linux)
```
Could not initialize GLFW
```
**Solution**: 
```bash
sudo apt-get install libglfw3 libglfw3-dev
```

---

## Next Steps

After Week 1 is working:
- **Week 2**: Add IK (inverse kinematics) for motion
- **Week 3**: Trajectory planning
- **Week 4**: Connect to Intent Interface (gaze → robot motion)
- **Week 5+**: Advanced features (obstacles, multi-arm, etc.)




