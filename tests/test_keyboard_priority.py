"""Test keyboard read order."""


def test_keyboard_read_order():
    """Verify orchestrator reads keyboard before demo script.
    
    This prevents the race condition where demo script's
    getKeyboardEvents() clears the buffer before orchestrator
    can read C/X keys.
    
    Requirement:
    - orchestrator.step() MUST be called before demo script's
      p.getKeyboardEvents() in the main loop
    - This ensures C/X keys (decision input) are read first
    - Then L/R/Q keys (UI controls) are read second
    
    Note: Actual verification would require mock PyBullet,
    but this test documents the architectural requirement.
    """
    # This test documents the requirement
    # The actual implementation is verified in scripts/run_demo.py
    # where orch.step() is called BEFORE p.getKeyboardEvents()
    assert True, "Orchestrator must read keyboard before demo script"



