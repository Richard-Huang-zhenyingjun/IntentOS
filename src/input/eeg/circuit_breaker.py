"""
Circuit breaker for EEG device reliability.

If device errors exceed threshold, trips the breaker:
- EEG source reports NONE + quality=0
- After cooldown, attempts to resume
- Never crashes or hangs the system
"""
import time
import logging

logger = logging.getLogger(__name__)


class EEGCircuitBreaker:
    """
    Monitors EEG device health and trips on excessive errors.
    
    States:
    - CLOSED: Normal operation
    - OPEN: Too many errors, blocking EEG
    - HALF_OPEN: Trying to resume after cooldown
    """
    
    def __init__(self, config: dict):
        breaker_cfg = config.get('eeg', {}).get('circuit_breaker', {})
        
        self.error_threshold = breaker_cfg.get('error_threshold', 10)
        self.cooldown_sec = breaker_cfg.get('cooldown_sec', 5.0)
        self.window_sec = breaker_cfg.get('window_sec', 10.0)
        
        # State
        self._state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        self._error_times: list = []
        self._trip_time: float = 0.0
        
        # Metrics
        self.trip_count: int = 0
    
    @property
    def is_allowing(self) -> bool:
        """Check if EEG operations are allowed"""
        if self._state == 'CLOSED':
            return True
        
        if self._state == 'OPEN':
            # Check if cooldown has elapsed
            if time.time() - self._trip_time > self.cooldown_sec:
                self._state = 'HALF_OPEN'
                logger.info("[BREAKER] Entering HALF_OPEN (attempting resume)")
                return True
            return False
        
        if self._state == 'HALF_OPEN':
            return True
        
        return False
    
    def record_success(self):
        """Record a successful EEG operation"""
        if self._state == 'HALF_OPEN':
            self._state = 'CLOSED'
            logger.info("[BREAKER] Resumed to CLOSED (success)")
    
    def record_error(self, error_msg: str = ""):
        """Record an EEG error"""
        now = time.time()
        self._error_times.append(now)
        
        # Prune old errors outside window
        cutoff = now - self.window_sec
        self._error_times = [t for t in self._error_times if t > cutoff]
        
        # Check threshold
        if len(self._error_times) >= self.error_threshold:
            if self._state != 'OPEN':
                self._state = 'OPEN'
                self._trip_time = now
                self.trip_count += 1
                logger.warning(
                    f"[BREAKER] TRIPPED (errors={len(self._error_times)} "
                    f"in {self.window_sec}s): {error_msg}"
                )
        
        if self._state == 'HALF_OPEN':
            # Failed during recovery
            self._state = 'OPEN'
            self._trip_time = now
            logger.warning("[BREAKER] Failed during HALF_OPEN, back to OPEN")
    
    def record_disconnect(self):
        """Device disconnected — trip immediately"""
        self._state = 'OPEN'
        self._trip_time = time.time()
        self.trip_count += 1
        logger.warning("[BREAKER] Device disconnected, TRIPPED immediately")
    
    def get_state(self) -> str:
        return self._state



