#!/usr/bin/env python3
"""
Diagnostic script to identify why demo won't run.
Run this to find the exact error.
"""

import sys
import os
from pathlib import Path

print("=" * 70)
print("INTENT INTERFACE DEMO STARTUP DIAGNOSTIC")
print("=" * 70)

# Step 1: Check Python environment
print("\n[1] PYTHON ENVIRONMENT")
print(f"    Python executable: {sys.executable}")
print(f"    Python version: {sys.version}")
print(f"    Working directory: {os.getcwd()}")

# Step 2: Check PyBullet
print("\n[2] PYBULLET CHECK")
try:
    import pybullet as p
    print(f"    ✓ PyBullet imported successfully")
    # Try to get version info (method may vary by version)
    try:
        version_info = p.getVersionInfo() if hasattr(p, 'getVersionInfo') else None
        if version_info:
            print(f"    ✓ Version: {version_info}")
    except:
        pass
    print(f"    ✓ Location: {p.__file__}")
except ImportError as e:
    print(f"    ✗ PyBullet import failed: {e}")
    sys.exit(1)

# Step 3: Check other dependencies
print("\n[3] DEPENDENCIES CHECK")
deps = {
    'numpy': 'numpy',
    'yaml': 'pyyaml',
}

for module, package in deps.items():
    try:
        mod = __import__(module)
        print(f"    ✓ {module}: {getattr(mod, '__version__', 'installed')}")
    except ImportError:
        print(f"    ✗ {module} NOT FOUND (install with: pip install {package})")

# Step 4: Check project structure
print("\n[4] PROJECT STRUCTURE CHECK")
required_paths = [
    'scripts/run_demo.py',
    'src/',
    'src/core/',
    'src/robot/',
    'src/input/',
    'configs/default.yaml',
]

for path in required_paths:
    exists = Path(path).exists()
    status = "✓" if exists else "✗"
    print(f"    {status} {path}")
    if not exists:
        print(f"        ERROR: Required path missing!")

# Step 5: Check Python path
print("\n[5] PYTHON PATH")
print(f"    sys.path entries:")
for i, p in enumerate(sys.path[:5]):
    print(f"      {i}: {p}")

# Step 6: Try importing src modules
print("\n[6] SRC MODULE IMPORTS")
src_modules = [
    'src.core.orchestrator',
    'src.core.schema',
    'src.robot.simulator',
    'src.input.keyboard_input',
]

for module in src_modules:
    try:
        # Add src to path if needed
        src_path = Path.cwd() / 'src'
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path.parent))
        
        parts = module.split('.')
        mod = __import__(module, fromlist=[parts[-1]])
        print(f"    ✓ {module}")
    except ImportError as e:
        print(f"    ✗ {module}")
        print(f"        Error: {e}")
    except Exception as e:
        print(f"    ⚠ {module} imported but error: {e}")

# Step 7: Try to actually run the demo script
print("\n[7] DEMO SCRIPT EXECUTION TEST")
demo_path = Path('scripts/run_demo.py')

if not demo_path.exists():
    print("    ✗ Demo script not found!")
else:
    print(f"    Found demo at: {demo_path}")
    print("    Attempting to import...")
    
    try:
        # Try to exec the demo script to see where it fails
        with open(demo_path, 'r') as f:
            code = f.read()
        
        # Execute in isolated namespace to catch errors
        namespace = {'__name__': '__main__', '__file__': str(demo_path)}
        
        # Try just the imports part
        import_section = []
        for line in code.split('\n'):
            if line.strip().startswith(('import ', 'from ')):
                import_section.append(line)
            elif import_section and not line.strip().startswith('#') and line.strip():
                break  # Stop at first non-import line
        
        imports_code = '\n'.join(import_section)
        print(f"    Testing {len(import_section)} import statements...")
        
        exec(imports_code, namespace)
        print("    ✓ All imports successful!")
        
    except Exception as e:
        print(f"    ✗ Error during import test:")
        print(f"        {type(e).__name__}: {e}")
        import traceback
        print("\n    Full traceback:")
        traceback.print_exc()

# Step 8: Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

print("\nIf you see errors above, the most common issues are:")
print("  1. Missing dependencies → Run: pip install pybullet numpy pyyaml")
print("  2. Wrong directory → cd to project root")
print("  3. Missing src/ files → Check git status")
print("  4. Python path issues → Check sys.path output above")

print("\nTo run the demo, try:")
print("  python scripts/run_demo.py")

print("\nIf still failing, run with:")
print("  python scripts/run_demo.py --help")
print("  (to see if argument parsing works)")

print("\n" + "=" * 70)

