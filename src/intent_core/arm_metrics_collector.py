"""
Arm metrics collector - comprehensive performance metrics.
Week 9: Quantify system behavior for evaluation and trust verification.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from collections import defaultdict
from .arm_ui_snapshot import ArmUISnapshot
from .arm_trust_metrics import ArmTrustMetrics


class ArmMetricsCollector:
    """
    Collects comprehensive metrics during execution.
    
    Tracks:
    - Trust and safety metrics
    - Execution statistics
    - Performance metrics
    - EEG quality metrics
    
    Week 9: Complete quantitative evaluation.
    """
    
    def __init__(self, trust_metrics: ArmTrustMetrics):
        """
        Initialize metrics collector.
        
        Args:
            trust_metrics: Trust metrics instance to track
        """
        self.trust_metrics = trust_metrics
        
        # Session info
        self.session_start = time.time()
        self.frame_count = 0
        
        # Performance tracking
        self.frame_times = []
        self.fps_samples = []
        
        # Action tracking
        self.action_counts = defaultdict(int)
        self.action_durations = defaultdict(list)
        
        # EEG quality tracking
        self.eeg_stable_frames = 0
        self.eeg_total_frames = 0
        self.eeg_attention_samples = []
        
        # Pause tracking
        self.pause_durations = []
        
        # Execution tracking
        self.execution_start_times = {}  # action_type -> start_time
    
    def update(self, snapshot: ArmUISnapshot, dt: float) -> None:
        """
        Update metrics from snapshot.
        
        Args:
            snapshot: Current UI snapshot
            dt: Delta time since last update
        """
        self.frame_count += 1
        self.frame_times.append(dt)
        
        # Track FPS
        if dt > 0:
            self.fps_samples.append(1.0 / dt)
        
        # Track EEG quality
        if snapshot.decision_source != "keyboard":
            self.eeg_total_frames += 1
            if snapshot.eeg_stable:
                self.eeg_stable_frames += 1
            
            if snapshot.eeg_attention is not None:
                self.eeg_attention_samples.append(snapshot.eeg_attention)
        
        # Track execution starts
        if snapshot.executing_action and snapshot.executing_action not in self.execution_start_times:
            self.execution_start_times[snapshot.executing_action] = time.time()
        
        # Track execution completions
        if snapshot.last_execution_result:
            action = snapshot.last_execution_result.get("action_type")
            if action and action in self.execution_start_times:
                duration = time.time() - self.execution_start_times[action]
                self.action_durations[action].append(duration)
                del self.execution_start_times[action]
                self.action_counts[action] += 1
    
    def finalize(self) -> Dict[str, Any]:
        """
        Finalize and return complete metrics.
        
        Returns:
            Dict with all metrics
        """
        session_duration = time.time() - self.session_start
        
        # Compute averages
        avg_fps = sum(self.fps_samples) / len(self.fps_samples) if self.fps_samples else 0.0
        avg_frame_time = sum(self.frame_times) / len(self.frame_times) if self.frame_times else 0.0
        
        eeg_stable_ratio = (self.eeg_stable_frames / self.eeg_total_frames 
                           if self.eeg_total_frames > 0 else 1.0)
        
        avg_attention = (sum(self.eeg_attention_samples) / len(self.eeg_attention_samples)
                        if self.eeg_attention_samples else None)
        
        # Action statistics
        action_stats = {}
        for action, durations in self.action_durations.items():
            action_stats[action] = {
                "count": len(durations),
                "avg_duration_s": sum(durations) / len(durations),
                "min_duration_s": min(durations),
                "max_duration_s": max(durations),
            }
        
        return {
            "session": {
                "duration_s": session_duration,
                "frame_count": self.frame_count,
            },
            "performance": {
                "avg_fps": avg_fps,
                "avg_frame_time_ms": avg_frame_time * 1000,
            },
            "trust": self.trust_metrics.get_summary(),
            "eeg_quality": {
                "stable_ratio": eeg_stable_ratio,
                "avg_attention": avg_attention,
                "total_frames": self.eeg_total_frames,
            },
            "actions": action_stats,
        }
    
    def save_json(self, filepath: Path) -> None:
        """
        Save metrics to JSON file.
        
        Args:
            filepath: Output file path
        """
        metrics = self.finalize()
        
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(metrics, f, indent=2)
        
        print(f"✓ Metrics saved: {filepath}")
    
    def print_summary(self) -> None:
        """Print metrics summary to console."""
        metrics = self.finalize()
        
        print("\n" + "="*70)
        print("PERFORMANCE & TRUST METRICS")
        print("="*70)
        
        # Session
        print(f"\nSession:")
        print(f"  Duration: {metrics['session']['duration_s']:.1f}s")
        print(f"  Frames: {metrics['session']['frame_count']}")
        print(f"  Avg FPS: {metrics['performance']['avg_fps']:.1f}")
        
        # Trust (most important)
        trust = metrics['trust']
        status = "✓ PASS" if trust['false_executions'] == 0 else "🚨 FAIL"
        print(f"\nTrust & Safety:")
        print(f"  False Executions: {trust['false_executions']} {status}")
        print(f"  Executions Started: {trust['executions_started']}")
        print(f"  Executions Completed: {trust['executions_completed']}")
        print(f"  Success Rate: {trust.get('success_rate', 0):.1f}%")
        print(f"  Blocked (unstable): {trust['blocked_unstable']}")
        print(f"  Pauses: {trust['pauses_triggered']}")
        
        # EEG quality
        if metrics['eeg_quality']['total_frames'] > 0:
            eeg = metrics['eeg_quality']
            print(f"\nEEG Quality:")
            print(f"  Stable Ratio: {eeg['stable_ratio']*100:.1f}%")
            if eeg['avg_attention']:
                print(f"  Avg Attention: {eeg['avg_attention']:.1f}")
        
        # Actions
        if metrics['actions']:
            print(f"\nActions:")
            for action, stats in metrics['actions'].items():
                print(f"  {action}: {stats['count']}x, avg {stats['avg_duration_s']:.2f}s")
        
        print("="*70 + "\n")
