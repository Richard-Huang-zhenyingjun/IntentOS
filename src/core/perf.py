import time
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class FrameTiming:
    """Per-frame performance breakdown."""

    frame_num: int
    total_ms: float
    orchestrator_ms: float
    overlay_ms: float
    metrics_ms: float
    physics_ms: float


class PerfMonitor:
    """Lightweight performance monitoring."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.samples: List[FrameTiming] = []
        self._start_times: Dict[str, float] = {}

    def start(self, label: str):
        if self.enabled:
            self._start_times[label] = time.perf_counter()

    def end(self, label: str) -> float:
        if not self.enabled:
            return 0.0
        start = self._start_times.get(label)
        if start is None:
            return 0.0
        return (time.perf_counter() - start) * 1000.0

    def record_frame(self, frame_timing: FrameTiming):
        if self.enabled:
            self.samples.append(frame_timing)

    def _percentile(self, values: List[float], q: float) -> float:
        if not values:
            return 0.0
        if q <= 0:
            return min(values)
        if q >= 1:
            return max(values)
        sorted_values = sorted(values)
        index = int(round((len(sorted_values) - 1) * q))
        index = max(0, min(index, len(sorted_values) - 1))
        return sorted_values[index]

    def summary(self) -> Dict[str, float]:
        """Return p50, p95, p99 for each component."""
        if not self.samples:
            return {
                "frames": 0.0,
                "orchestrator_p50_ms": 0.0,
                "orchestrator_p95_ms": 0.0,
                "orchestrator_p99_ms": 0.0,
                "overlay_p50_ms": 0.0,
                "overlay_p95_ms": 0.0,
                "overlay_p99_ms": 0.0,
                "metrics_p50_ms": 0.0,
                "metrics_p95_ms": 0.0,
                "metrics_p99_ms": 0.0,
                "physics_p50_ms": 0.0,
                "physics_p95_ms": 0.0,
                "physics_p99_ms": 0.0,
                "total_p50_ms": 0.0,
                "total_p95_ms": 0.0,
                "total_p99_ms": 0.0,
            }

        orchestrator = [s.orchestrator_ms for s in self.samples]
        overlay = [s.overlay_ms for s in self.samples]
        metrics = [s.metrics_ms for s in self.samples]
        physics = [s.physics_ms for s in self.samples]
        total = [s.total_ms for s in self.samples]

        return {
            "frames": float(len(self.samples)),
            "orchestrator_p50_ms": self._percentile(orchestrator, 0.50),
            "orchestrator_p95_ms": self._percentile(orchestrator, 0.95),
            "orchestrator_p99_ms": self._percentile(orchestrator, 0.99),
            "overlay_p50_ms": self._percentile(overlay, 0.50),
            "overlay_p95_ms": self._percentile(overlay, 0.95),
            "overlay_p99_ms": self._percentile(overlay, 0.99),
            "metrics_p50_ms": self._percentile(metrics, 0.50),
            "metrics_p95_ms": self._percentile(metrics, 0.95),
            "metrics_p99_ms": self._percentile(metrics, 0.99),
            "physics_p50_ms": self._percentile(physics, 0.50),
            "physics_p95_ms": self._percentile(physics, 0.95),
            "physics_p99_ms": self._percentile(physics, 0.99),
            "total_p50_ms": self._percentile(total, 0.50),
            "total_p95_ms": self._percentile(total, 0.95),
            "total_p99_ms": self._percentile(total, 0.99),
        }
