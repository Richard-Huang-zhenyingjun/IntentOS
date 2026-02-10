"""Session metrics collection for demo runs."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional
import time
import uuid


@dataclass
class SessionMetrics:
    """Aggregated metrics for a demo session."""

    session_id: str
    start_time: float
    end_time: float

    # Proposals
    proposals_generated: int
    proposals_confirmed: int
    proposals_cancelled: int

    # Execution
    objects_attempted: int
    objects_succeeded: int
    objects_failed: int
    primitives_executed: int
    primitives_failed: int

    # Trust
    trust_penalties: int
    trust_recoveries: int
    min_trust: float
    max_trust: float
    reauth_events: int

    # Safety
    false_executions: int  # Must always be 0

    # Timing
    total_execution_time: float
    avg_time_per_object: float

    # Failures
    timeout_aborts: int
    grasp_failures: int
    unreachable_skips: int


class MetricsCollector:
    """Real-time metrics aggregation from event stream + snapshots."""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or f"sess_{uuid.uuid4().hex[:10]}"
        self.start_time = time.time()
        self.metrics = SessionMetrics(
            session_id=self.session_id,
            start_time=self.start_time,
            end_time=self.start_time,
            proposals_generated=0,
            proposals_confirmed=0,
            proposals_cancelled=0,
            objects_attempted=0,
            objects_succeeded=0,
            objects_failed=0,
            primitives_executed=0,
            primitives_failed=0,
            trust_penalties=0,
            trust_recoveries=0,
            min_trust=1.0,
            max_trust=1.0,
            reauth_events=0,
            false_executions=0,
            total_execution_time=0.0,
            avg_time_per_object=0.0,
            timeout_aborts=0,
            grasp_failures=0,
            unreachable_skips=0,
        )
        self._last_state: Optional[str] = None
        self._seen_object_ids: set[int] = set()
        self._seen_primitives: set[tuple[int, int]] = set()  # (frame, primitive_index)

    def process_event(self, event: Dict[str, Any]) -> None:
        """Update metrics from an event dict."""
        event_type = event.get("event_type") or event.get("type") or ""
        raw_data = event.get("data")
        data: Dict[str, Any] = raw_data if isinstance(raw_data, dict) else event

        if event_type in ("proposal_generated", "proposal_issued"):
            self.metrics.proposals_generated += 1
        elif event_type in ("confirmed", "confirm_received", "auth_token_issued"):
            self.metrics.proposals_confirmed += 1
        elif event_type in ("cancelled", "decision_rejected"):
            self.metrics.proposals_cancelled += 1

        elif event_type == "primitive_completed":
            self.metrics.primitives_executed += 1
            status = str(data.get("status", "")).lower()
            if status in ("failed", "error"):
                self.metrics.primitives_failed += 1

        elif event_type == "object_started":
            self.metrics.objects_attempted += 1

        elif event_type == "object_completed":
            self.metrics.objects_attempted += 1
            status = str(data.get("status", "")).lower()
            if status in ("success", "completed", "ok"):
                self.metrics.objects_succeeded += 1
            else:
                self.metrics.objects_failed += 1

        elif event_type == "trust_updated":
            trust = data.get("task_trust")
            if isinstance(trust, (int, float)):
                self.metrics.min_trust = min(self.metrics.min_trust, float(trust))
                self.metrics.max_trust = max(self.metrics.max_trust, float(trust))

            trust_event = str(data.get("event", "")).lower()
            if any(k in trust_event for k in ("fail", "timeout", "penalty", "skip", "error")):
                self.metrics.trust_penalties += 1
            elif any(k in trust_event for k in ("recover", "success")):
                self.metrics.trust_recoveries += 1

            if "timeout" in trust_event:
                self.metrics.timeout_aborts += 1
            if "grasp" in trust_event and "fail" in trust_event:
                self.metrics.grasp_failures += 1
            if "unreachable" in trust_event:
                self.metrics.unreachable_skips += 1

        elif event_type == "trust_reauth_triggered":
            self.metrics.reauth_events += 1

    def process_snapshot(self, snapshot: Any) -> None:
        """Update metrics from per-frame snapshot state."""
        try:
            state_value = snapshot.state.value if hasattr(snapshot.state, "value") else str(snapshot.state)
        except Exception:
            state_value = "unknown"

        # Derive proposal generation from SELECTING -> CONFIRMING transitions.
        if self._last_state == "selecting" and state_value == "confirming":
            self.metrics.proposals_generated += 1

        # Derive cancellations from CONFIRMING -> IDLE transitions.
        if self._last_state == "confirming" and state_value == "idle":
            self.metrics.proposals_cancelled += 1

        if hasattr(snapshot, "task_trust") and snapshot.task_trust is not None:
            trust = float(snapshot.task_trust)
            self.metrics.min_trust = min(self.metrics.min_trust, trust)
            self.metrics.max_trust = max(self.metrics.max_trust, trust)

        if hasattr(snapshot, "false_executions"):
            self.metrics.false_executions = max(self.metrics.false_executions, int(snapshot.false_executions))

        # Approximate primitive progression from primitive index while executing.
        if state_value == "executing" and hasattr(snapshot, "primitive_index"):
            frame = int(getattr(snapshot, "frame_count", 0))
            prim = int(snapshot.primitive_index)
            key = (frame, prim)
            if key not in self._seen_primitives:
                self._seen_primitives.add(key)
                self.metrics.primitives_executed = max(self.metrics.primitives_executed, prim)

        self._last_state = state_value

    def finalize(self) -> SessionMetrics:
        """Compute derived metrics and return finalized session metrics."""
        self.metrics.end_time = time.time()
        self.metrics.total_execution_time = self.metrics.end_time - self.start_time

        if self.metrics.objects_succeeded > 0:
            self.metrics.avg_time_per_object = (
                self.metrics.total_execution_time / self.metrics.objects_succeeded
            )

        return self.metrics

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self.metrics)
