#!/usr/bin/env python3
"""
Fix imports in all src/ files to remove src. prefix.

When files are inside src/, they should import without the src. prefix
since scripts add src/ to sys.path.
"""

import re
from pathlib import Path

def fix_imports_in_file(file_path: Path):
    """Fix all src. imports in a file"""
    content = file_path.read_text()
    original_content = content
    
    # Replace "from src." with "from "
    content = re.sub(r'^from src\.', 'from ', content, flags=re.MULTILINE)
    
    # Replace "import src." with "import " (less common but check anyway)
    content = re.sub(r'^import src\.', 'import ', content, flags=re.MULTILINE)
    
    if content != original_content:
        file_path.write_text(content)
        return True
    return False

def main():
    src_dir = Path(__file__).parent / 'src'
    
    if not src_dir.exists():
        print(f"❌ src/ directory not found at {src_dir}")
        return
    
    print("🔧 Fixing imports in src/ directory...")
    print()
    
    fixed_count = 0
    total_count = 0
    
    # Find all .py files in src/
    for py_file in src_dir.rglob('*.py'):
        if py_file.name == '__pycache__':
            continue
        
        total_count += 1
        relative_path = py_file.relative_to(src_dir.parent)
        
        if fix_imports_in_file(py_file):
            print(f"✅ Fixed: {relative_path}")
            fixed_count += 1
    
    print()
    print(f"📊 Results:")
    print(f"   Total files: {total_count}")
    print(f"   Fixed: {fixed_count}")
    print(f"   Unchanged: {total_count - fixed_count}")
    
    if fixed_count > 0:
        print()
        print("✨ All imports fixed! You can now run:")
        print("   python scripts/run_unified_demo.py --mode full_narrative")

if __name__ == '__main__':
    main()






