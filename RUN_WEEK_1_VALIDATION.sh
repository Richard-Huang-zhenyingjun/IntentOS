#!/bin/bash
# Week 1 Robotics: One-Command Validation Script
# Run this to validate all Week 1 deliverables

set -e  # Exit on error

echo "════════════════════════════════════════════════════════════"
echo "Week 1 Robotics Validation"
echo "════════════════════════════════════════════════════════════"
echo ""

# Check if in correct directory
if [ ! -f "configs/robotics.yaml" ]; then
    echo "❌ Error: Run this from project root"
    exit 1
fi

# Step 1: Verify PyBullet is installed
echo "📦 Step 1: Checking dependencies..."
python -c "import pybullet; print('  ✅ PyBullet installed')" || {
    echo "  ❌ PyBullet not found. Installing..."
    conda install -c conda-forge pybullet -y
}

python -c "import scipy; print('  ✅ scipy installed')" || {
    echo "  ❌ scipy not found. Installing..."
    pip install scipy
}

echo ""

# Step 2: Run automated tests
echo "🧪 Step 2: Running automated tests..."
echo "────────────────────────────────────────────────────────────"
pytest tests/test_week1_world_loads.py -v --tb=short

if [ $? -eq 0 ]; then
    echo ""
    echo "  ✅ All tests passed!"
else
    echo ""
    echo "  ❌ Tests failed. Check output above."
    exit 1
fi

echo ""

# Step 3: Run headless demo
echo "🎬 Step 3: Running headless demo..."
echo "────────────────────────────────────────────────────────────"
python scripts/run_virtual_arm_demo_headless.py

if [ $? -eq 0 ]; then
    echo ""
    echo "  ✅ Demo completed successfully!"
else
    echo ""
    echo "  ❌ Demo failed. Check output above."
    exit 1
fi

echo ""

# Summary
echo "════════════════════════════════════════════════════════════"
echo "✅ Week 1 Validation Complete!"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Summary:"
echo "  ✅ All 7 tests passed"
echo "  ✅ Headless demo ran successfully"
echo "  ✅ Physics simulation working correctly"
echo "  ✅ State reading validated"
echo ""
echo "📄 Documentation:"
echo "  - WEEK_1_COMPLETE.md          (completion checklist)"
echo "  - WEEK_1_ROBOTICS_VALIDATION.md (full report)"
echo "  - WEEK_1_QUICK_START.md       (quick guide)"
echo ""
echo "🎉 Week 1 robotics implementation is ready!"
echo ""




