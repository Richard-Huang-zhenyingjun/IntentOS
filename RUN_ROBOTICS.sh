#!/bin/bash

# Quick Start Script for Robotics Module (Week 1)
# Helps set up Python 3.12 environment and run demo

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║  🦾 INTENT INTERFACE - ROBOTICS MODULE SETUP                  ║"
echo "║     Week 1: Virtual Arm Simulation                            ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Check Python version
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

echo "📍 Current Python: $PYTHON_VERSION"
echo ""

if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -eq 13 ]; then
    echo "⚠️  Python 3.13 detected - PyBullet not compatible yet!"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "SOLUTION: Create Python 3.12 environment"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Option 1 - Conda (recommended):"
    echo "  conda create -n intent-robotics python=3.12 -y"
    echo "  conda activate intent-robotics"
    echo "  pip install -r requirements.txt"
    echo "  bash RUN_ROBOTICS.sh"
    echo ""
    echo "Option 2 - pyenv:"
    echo "  pyenv install 3.12.0"
    echo "  pyenv local 3.12.0"
    echo "  python -m venv .venv-robotics"
    echo "  source .venv-robotics/bin/activate"
    echo "  pip install -r requirements.txt"
    echo "  bash RUN_ROBOTICS.sh"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi

# Check if PyBullet is installed
echo "🔍 Checking PyBullet installation..."
if python -c "import pybullet" 2>/dev/null; then
    PYBULLET_VERSION=$(python -c "import pybullet as p; print(p.getVersionInfo())")
    echo "✅ PyBullet installed: $PYBULLET_VERSION"
else
    echo "❌ PyBullet not found"
    echo ""
    echo "Installing dependencies..."
    pip install -r requirements.txt
    echo "✅ Dependencies installed"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 RUNNING WEEK 1 DEMO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Starting virtual arm simulation..."
echo ""
echo "Controls:"
echo "  - Mouse: Rotate view"
echo "  - Mouse wheel: Zoom"
echo "  - ENTER: Print state"
echo "  - CTRL+C / Q: Quit"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Run demo
python scripts/run_virtual_arm_demo.py

echo ""
echo "✅ Demo complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "NEXT STEPS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Run tests:"
echo "  pytest tests/test_week1_world_loads.py -v"
echo ""
echo "Read documentation:"
echo "  docs/ROBOTICS_README.md"
echo "  docs/ROBOTICS_SETUP.md"
echo ""
echo "Week 2 preview:"
echo "  - Inverse kinematics (IK)"
echo "  - Robot motion"
echo "  - Trajectory planning"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"




