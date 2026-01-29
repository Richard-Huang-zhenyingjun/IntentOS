"""Trust metrics tracking - CRITICAL: false_executions must always be 0."""


class TrustMetrics:
    """Track execution safety metrics."""
    
    def __init__(self):
        self.false_executions = 0  # CRITICAL INVARIANT
        self.confirmed_executions = 0
        self.pauses_triggered = 0
        self.confirmations_received = 0
        self.confirmations_blocked = 0
    
    def record_execution(self, was_confirmed: bool):
        """Record execution attempt."""
        if was_confirmed:
            self.confirmed_executions += 1
        else:
            self.false_executions += 1
            # This should NEVER happen - log critical error
            print(f"❌ CRITICAL: FALSE EXECUTION DETECTED!")
    
    def record_confirmation(self, allowed: bool):
        """Record confirmation attempt."""
        self.confirmations_received += 1
        if not allowed:
            self.confirmations_blocked += 1
    
    def record_pause(self):
        """Record pause event."""
        self.pauses_triggered += 1
    
    def get_summary(self) -> dict:
        """Get metrics summary."""
        return {
            'false_executions': self.false_executions,
            'confirmed_executions': self.confirmed_executions,
            'pauses_triggered': self.pauses_triggered,
            'confirmations_received': self.confirmations_received,
            'confirmations_blocked': self.confirmations_blocked,
        }

