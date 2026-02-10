# Environment Issue Report
**Date:** January 29, 2025  
**Issue:** PyBullet Installation and Environment Mismatch

## Executive Summary

PyBullet was successfully installed via conda-forge into the `intent_interface` conda environment (Python 3.12), but the demo script fails because it's being executed with a different Python interpreter (base Anaconda Python 3.13) that doesn't have PyBullet installed.

---

## Timeline of Events

### Phase 1: Initial PyBullet Installation Failure (Lines 824-837)
**Problem:** Attempted to install PyBullet via pip failed
- **Error:** `ERROR: Failed building wheel for pybullet`
- **Root Cause:** Python 3.13.5 is too new - PyBullet doesn't have pre-built wheels for Python 3.13 yet
- **Attempted Solution:** Building from source failed with clang compilation errors

### Phase 2: Build Tools Check (Lines 838-843)
**Action:** Verified Xcode Command Line Tools
- **Result:** Already installed (no action needed)
- **Status:** Not the issue

### Phase 3: Successful Conda Installation (Lines 844-938)
**Action:** Installed PyBullet via conda-forge
```bash
conda install -c conda-forge pybullet
```

**Result:** ✅ **SUCCESS**
- PyBullet 3.25 installed
- Python downgraded from 3.12.12 → 3.12.8 (to match conda-forge package)
- Environment: `/opt/anaconda3/envs/intent_interface`
- All dependencies resolved (numpy, bullet-cpp, etc.)

### Phase 4: Demo Script Failure (Lines 939-968)
**Problem:** Demo script still fails with `ModuleNotFoundError: No module named 'pybullet'`

**Root Cause Identified:**
- PyBullet is installed in: `intent_interface` conda environment (Python 3.12)
- Demo script is running with: Base Anaconda Python 3.13
- **Environment mismatch!**

### Phase 5: Debug Script Confusion (Lines 969-978)
**Issue:** User tried to run `debug_demo_startup.py` which doesn't exist
- **Correct filename:** `scripts/diagnose.py` (already created)

---

## Technical Analysis

### Current Environment State

| Component | Location | Python Version | PyBullet Status |
|-----------|----------|----------------|-----------------|
| **Base Anaconda** | `/opt/anaconda3/bin/python` | 3.13.5 | ❌ Not installed |
| **Conda Env** | `/opt/anaconda3/envs/intent_interface/bin/python` | 3.12.8 | ✅ Installed (3.25) |
| **Current `python` command** | Points to base Anaconda | 3.13.5 | ❌ No PyBullet |

### Why It Fails

1. **Terminal shows:** `(intent_interface) (.venv)` - suggests conda env is active
2. **But `python` command resolves to:** `/opt/anaconda3/bin/python` (base, not conda env)
3. **PyBullet is in:** `/opt/anaconda3/envs/intent_interface/` (conda env)
4. **Result:** Python can't find PyBullet because it's looking in the wrong environment

### Environment Detection Issue

The prompt shows `(intent_interface)` but the Python interpreter is from base Anaconda. This suggests:
- Conda environment may not be properly activated
- OR `.venv` virtual environment is interfering
- OR PATH is not correctly set

---

## Solutions

### ✅ Solution 1: Activate Conda Environment Properly (RECOMMENDED)

```bash
# Deactivate any virtual environments
deactivate  # if .venv is active

# Activate conda environment
conda activate intent_interface

# Verify Python path
which python
# Should show: /opt/anaconda3/envs/intent_interface/bin/python

# Verify PyBullet
python -c "import pybullet; print('✓ PyBullet works')"

# Run demo
python scripts/run_demo.py
```

### ✅ Solution 2: Use Full Path to Conda Python

```bash
/opt/anaconda3/envs/intent_interface/bin/python scripts/run_demo.py
```

### ✅ Solution 3: Install PyBullet in Base Anaconda (Not Recommended)

```bash
# Switch to base environment
conda deactivate

# Install PyBullet (may need Python 3.12)
conda install -c conda-forge pybullet python=3.12
```

### ✅ Solution 4: Use Diagnostic Script

```bash
# Run the diagnostic script (correct filename)
python scripts/diagnose.py
```

This will show exactly which Python is being used and what's missing.

---

## Recommendations

1. **Use conda environment consistently:**
   - Always activate `intent_interface` before running scripts
   - Consider adding activation to your shell profile

2. **Remove conflicting virtual environments:**
   - The `.venv` directory may be causing confusion
   - Consider removing it if using conda environments

3. **Update PATH:**
   - Ensure conda environment Python is first in PATH when activated
   - Check: `echo $PATH | tr ':' '\n' | grep python`

4. **Use diagnostic script:**
   - Run `python scripts/diagnose.py` to verify setup
   - This will catch environment issues early

---

## Verification Steps

After applying Solution 1, verify:

```bash
# 1. Check Python version
python --version
# Expected: Python 3.12.8

# 2. Check Python path
which python
# Expected: /opt/anaconda3/envs/intent_interface/bin/python

# 3. Verify PyBullet
python -c "import pybullet; print('✓ PyBullet:', pybullet.__file__)"
# Expected: ✓ PyBullet: /opt/anaconda3/envs/intent_interface/lib/python3.12/site-packages/...

# 4. Run diagnostic
python scripts/diagnose.py
# Expected: All checks pass

# 5. Run demo
python scripts/run_demo.py --help
# Expected: Shows help message
```

---

## Summary

**Status:** ✅ PyBullet is installed correctly  
**Issue:** Environment activation mismatch  
**Fix:** Activate conda environment before running scripts  
**Prevention:** Use `scripts/diagnose.py` to verify setup

---

## Files Created

- `scripts/diagnose.py` - Diagnostic script to identify environment issues
- `ENVIRONMENT_ISSUE_REPORT.md` - This report


