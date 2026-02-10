#!/bin/bash
# Wrapper script to run unified arm demo with correct Python environment
# Uses conda base Python which has pybullet installed

cd "$(dirname "$0")"

# Use conda base Python directly (has pybullet installed)
/opt/anaconda3/bin/python scripts/run_unified_arm_demo.py "$@"





