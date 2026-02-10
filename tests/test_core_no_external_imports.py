"""
Test that core modules don't import external libraries or concrete implementations.

This is GPT's brilliant insight: catch boundary violations at import time.
"""
import pytest
import ast
import os
from pathlib import Path


# Modules that src/core/ is NEVER allowed to import
FORBIDDEN_IMPORTS_IN_CORE = {
    'google',            # Gemini
    'google.generativeai',
    'mne',               # MNE-Python
    'brainflow',         # BrainLink
    'requests',          # HTTP client (use adapters)
    # Concrete implementations
    'src.intelligence.proposer_heuristic',
    'src.intelligence.proposer_gemini',
    'src.external',
    'src.worlds',        # World builders injected, not imported
}

# Modules that src/execution/ is NEVER allowed to import
FORBIDDEN_IMPORTS_IN_EXECUTION = {
    'google',
    'google.generativeai',
    'mne',
    'brainflow',
    'src.external',
}

CORE_DIR = Path('src/core')
EXECUTION_DIR = Path('src/execution')


def _get_imports_from_file(filepath: Path) -> set:
    """Parse Python file and extract all import module names"""
    with open(filepath, 'r') as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return set()
    
    imports = set()
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
                # Also check parent modules
                parts = node.module.split('.')
                for i in range(1, len(parts) + 1):
                    imports.add('.'.join(parts[:i]))
    
    return imports


def _check_directory_imports(directory: Path, forbidden: set, exclude_files: set = None) -> list:
    """Check all Python files in directory for forbidden imports"""
    violations = []
    
    if not directory.exists():
        return violations
    
    if exclude_files is None:
        exclude_files = set()
    
    for py_file in directory.glob('*.py'):
        if py_file.name == '__init__.py':
            continue
        
        # Skip excluded files (e.g., system_factory.py is allowed to import concrete types)
        if py_file.name in exclude_files:
            continue
        
        imports = _get_imports_from_file(py_file)
        
        for forbidden_import in forbidden:
            if forbidden_import in imports:
                violations.append(
                    f"{py_file.name} imports '{forbidden_import}'"
                )
    
    return violations


def test_core_has_no_external_imports():
    """
    src/core/ must not import external libraries or concrete implementations.
    
    Exception: system_factory.py is the composition root and IS allowed to import
    concrete implementations (that's its purpose).
    
    Allowed: src.interfaces, src.intelligence.proposer_registry, 
             src.execution.task_executor, src.execution.primitive_executor,
             src.robot.*, standard library
    """
    # system_factory.py is the composition root - it MUST import concrete types
    violations = _check_directory_imports(
        CORE_DIR, 
        FORBIDDEN_IMPORTS_IN_CORE,
        exclude_files={'system_factory.py'}
    )
    
    assert len(violations) == 0, (
        f"Core boundary violations found:\n" +
        "\n".join(f"  ❌ {v}" for v in violations)
    )


def test_execution_has_no_external_imports():
    """
    src/execution/ must not import external libraries.
    
    Allowed: src.interfaces, src.robot.*, standard library
    """
    violations = _check_directory_imports(EXECUTION_DIR, FORBIDDEN_IMPORTS_IN_EXECUTION)
    
    assert len(violations) == 0, (
        f"Execution boundary violations found:\n" +
        "\n".join(f"  ❌ {v}" for v in violations)
    )


def test_interfaces_are_self_contained():
    """
    src/interfaces/ must not import from src/core/, src/execution/, 
    src/intelligence/, or src/external/.
    
    Interfaces can only import: standard library, numpy, typing
    """
    interfaces_dir = Path('src/interfaces')
    
    forbidden_for_interfaces = {
        'src.core',
        'src.execution',
        'src.intelligence',
        'src.external',
        'src.robot',
        'src.worlds',
        'src.planning',
    }
    
    violations = _check_directory_imports(interfaces_dir, forbidden_for_interfaces)
    
    assert len(violations) == 0, (
        f"Interface self-containment violations:\n" +
        "\n".join(f"  ❌ {v}" for v in violations)
    )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

