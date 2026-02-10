import sys
import os
from pathlib import Path

def print_startup_banner():
    """Print once at startup to verify execution paths"""
    print("="*60)
    print("[DIAG] Startup Environment Check")
    print("="*60)
    print(f"[DIAG] Python: {sys.executable}")
    print(f"[DIAG] CWD: {os.getcwd()}")
    print(f"[DIAG] Repo root: {Path(__file__).parent.parent.parent}")
    print("="*60)

def diag_print(msg: str, enabled: bool = True):
    """Conditional diagnostic print"""
    if enabled:
        print(f"[DIAG] {msg}")


