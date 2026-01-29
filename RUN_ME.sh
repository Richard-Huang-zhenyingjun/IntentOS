#!/bin/bash

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║        🎯 INTENT INTERFACE - QUICK START SCRIPT 🎯            ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "This will:"
echo "  1. Install YOLOv8 (if not already installed)"
echo "  2. Run the complete demo with object recognition"
echo ""
echo "Press ENTER to continue, or Ctrl+C to cancel..."
read

echo ""
echo "Installing YOLOv8..."
pip install ultralytics

echo ""
echo "Starting Intent Interface..."
echo ""
python scripts/run_complete_demo.py

