"""
Arm Metrics Report Generator
Week 9: Generate comprehensive reports from session metrics.

Usage:
    # Generate report for latest session
    python scripts/generate_arm_metrics_report.py --latest
    
    # Generate report for specific session
    python scripts/generate_arm_metrics_report.py --session arm_20250114_153022
    
    # Generate with comparison
    python scripts/generate_arm_metrics_report.py --latest --compare logs/arm_baseline_metrics.json
    
    # Export formats
    python scripts/generate_arm_metrics_report.py --latest --format markdown,json,console
"""

import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

sys.path.insert(0, 'src')


def find_latest_session(log_dir: Path) -> Optional[Path]:
    """
    Find latest metrics JSON file.
    
    Args:
        log_dir: Logs directory
        
    Returns:
        Path to latest metrics file, or None
    """
    metrics_files = list(log_dir.glob("*_metrics.json"))
    if not metrics_files:
        return None
    
    # Sort by modification time
    metrics_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return metrics_files[0]


def load_metrics(filepath: Path) -> Dict[str, Any]:
    """Load metrics from JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def generate_console_report(metrics: Dict[str, Any], comparison: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate console report.
    
    Args:
        metrics: Metrics dict
        comparison: Optional baseline metrics for comparison
        
    Returns:
        Report string
    """
    lines = []
    
    lines.append("=" * 70)
    lines.append("ARM METRICS REPORT")
    lines.append("=" * 70)
    
    # Session info
    session = metrics.get('session', {})
    lines.append(f"\nSession:")
    lines.append(f"  Duration: {session.get('duration_s', 0):.1f}s")
    lines.append(f"  Frames: {session.get('frame_count', 0)}")
    
    # Performance
    perf = metrics.get('performance', {})
    lines.append(f"\nPerformance:")
    lines.append(f"  Avg FPS: {perf.get('avg_fps', 0):.1f}")
    lines.append(f"  Avg Frame Time: {perf.get('avg_frame_time_ms', 0):.2f}ms")
    
    # Trust & Safety (CRITICAL)
    trust = metrics.get('trust', {})
    false_exec = trust.get('false_executions', 0)
    status = "✓ PASS" if false_exec == 0 else "🚨 FAIL"
    
    lines.append(f"\nTrust & Safety:")
    lines.append(f"  False Executions: {false_exec} {status}")
    lines.append(f"  Executions Started: {trust.get('executions_started', 0)}")
    lines.append(f"  Executions Completed: {trust.get('executions_completed', 0)}")
    lines.append(f"  Success Rate: {trust.get('success_rate', 0):.1f}%")
    lines.append(f"  Blocked (unstable): {trust.get('blocked_unstable', 0)}")
    lines.append(f"  Pauses Triggered: {trust.get('pauses_triggered', 0)}")
    
    # Pause breakdown
    pauses_by_trigger = trust.get('pauses_by_trigger', {})
    if pauses_by_trigger:
        lines.append(f"\n  Pause Breakdown:")
        for trigger, count in pauses_by_trigger.items():
            lines.append(f"    {trigger}: {count}")
    
    # EEG Quality
    eeg = metrics.get('eeg_quality', {})
    if eeg.get('total_frames', 0) > 0:
        lines.append(f"\nEEG Quality:")
        lines.append(f"  Stable Ratio: {eeg.get('stable_ratio', 0) * 100:.1f}%")
        if eeg.get('avg_attention'):
            lines.append(f"  Avg Attention: {eeg.get('avg_attention', 0):.1f}")
        lines.append(f"  Total Frames: {eeg.get('total_frames', 0)}")
    
    # Action statistics
    actions = metrics.get('actions', {})
    if actions:
        lines.append(f"\nAction Statistics:")
        for action, stats in actions.items():
            action_display = action.replace('_', ' ').title()
            lines.append(f"  {action_display}:")
            lines.append(f"    Count: {stats.get('count', 0)}")
            lines.append(f"    Avg Duration: {stats.get('avg_duration_s', 0):.2f}s")
            lines.append(f"    Min/Max: {stats.get('min_duration_s', 0):.2f}s / {stats.get('max_duration_s', 0):.2f}s")
    
    # Comparison section
    if comparison:
        lines.append(f"\n" + "=" * 70)
        lines.append("COMPARISON TO BASELINE")
        lines.append("=" * 70)
        
        comp_trust = comparison.get('trust', {})
        
        # Compare false executions
        baseline_false = comp_trust.get('false_executions', 0)
        current_false = trust.get('false_executions', 0)
        diff = current_false - baseline_false
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        lines.append(f"False Executions: {baseline_false} → {current_false} ({diff_str})")
        
        # Compare success rate
        baseline_success = comp_trust.get('success_rate', 0)
        current_success = trust.get('success_rate', 0)
        diff = current_success - baseline_success
        diff_str = f"+{diff:.1f}%" if diff > 0 else f"{diff:.1f}%"
        lines.append(f"Success Rate: {baseline_success:.1f}% → {current_success:.1f}% ({diff_str})")
        
        # Compare EEG stability
        if eeg.get('total_frames', 0) > 0 and comparison.get('eeg_quality', {}).get('total_frames', 0) > 0:
            baseline_stable = comparison.get('eeg_quality', {}).get('stable_ratio', 0)
            current_stable = eeg.get('stable_ratio', 0)
            diff = current_stable - baseline_stable
            diff_str = f"+{diff*100:.1f}%" if diff > 0 else f"{diff*100:.1f}%"
            lines.append(f"EEG Stability: {baseline_stable*100:.1f}% → {current_stable*100:.1f}% ({diff_str})")
    
    lines.append("=" * 70)
    
    return "\n".join(lines)


def generate_markdown_report(metrics: Dict[str, Any], comparison: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate markdown report.
    
    Args:
        metrics: Metrics dict
        comparison: Optional baseline metrics
        
    Returns:
        Markdown string
    """
    lines = []
    
    lines.append("# Arm Control System Metrics Report")
    lines.append("")
    lines.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # Session
    session = metrics.get('session', {})
    lines.append("## Session Information")
    lines.append("")
    lines.append(f"- **Duration**: {session.get('duration_s', 0):.1f}s")
    lines.append(f"- **Frames**: {session.get('frame_count', 0)}")
    lines.append("")
    
    # Performance
    perf = metrics.get('performance', {})
    lines.append("## Performance")
    lines.append("")
    lines.append(f"- **Average FPS**: {perf.get('avg_fps', 0):.1f}")
    lines.append(f"- **Average Frame Time**: {perf.get('avg_frame_time_ms', 0):.2f}ms")
    lines.append("")
    
    # Trust & Safety
    trust = metrics.get('trust', {})
    false_exec = trust.get('false_executions', 0)
    status = "✅ PASS" if false_exec == 0 else "🚨 FAIL"
    
    lines.append("## Trust & Safety Guarantees")
    lines.append("")
    lines.append("| Metric | Value | Status |")
    lines.append("|--------|-------|--------|")
    lines.append(f"| False Executions | {false_exec} | {status} |")
    lines.append(f"| Executions Started | {trust.get('executions_started', 0)} | - |")
    lines.append(f"| Executions Completed | {trust.get('executions_completed', 0)} | - |")
    lines.append(f"| Success Rate | {trust.get('success_rate', 0):.1f}% | - |")
    lines.append(f"| Blocked (Unstable) | {trust.get('blocked_unstable', 0)} | - |")
    lines.append(f"| Pauses Triggered | {trust.get('pauses_triggered', 0)} | - |")
    lines.append("")
    
    # Pause breakdown
    pauses_by_trigger = trust.get('pauses_by_trigger', {})
    if pauses_by_trigger:
        lines.append("### Pause Breakdown")
        lines.append("")
        for trigger, count in pauses_by_trigger.items():
            lines.append(f"- **{trigger}**: {count}")
        lines.append("")
    
    # EEG Quality
    eeg = metrics.get('eeg_quality', {})
    if eeg.get('total_frames', 0) > 0:
        lines.append("## EEG Quality")
        lines.append("")
        lines.append(f"- **Stable Ratio**: {eeg.get('stable_ratio', 0) * 100:.1f}%")
        if eeg.get('avg_attention'):
            lines.append(f"- **Average Attention**: {eeg.get('avg_attention', 0):.1f}")
        lines.append(f"- **Total Frames**: {eeg.get('total_frames', 0)}")
        lines.append("")
    
    # Actions
    actions = metrics.get('actions', {})
    if actions:
        lines.append("## Action Statistics")
        lines.append("")
        lines.append("| Action | Count | Avg Duration | Min/Max |")
        lines.append("|--------|-------|--------------|---------|")
        for action, stats in actions.items():
            action_display = action.replace('_', ' ').title()
            lines.append(
                f"| {action_display} | "
                f"{stats.get('count', 0)} | "
                f"{stats.get('avg_duration_s', 0):.2f}s | "
                f"{stats.get('min_duration_s', 0):.2f}s / {stats.get('max_duration_s', 0):.2f}s |"
            )
        lines.append("")
    
    # Comparison
    if comparison:
        lines.append("## Comparison to Baseline")
        lines.append("")
        comp_trust = comparison.get('trust', {})
        
        lines.append("| Metric | Baseline | Current | Change |")
        lines.append("|--------|----------|---------|--------|")
        
        # False executions
        baseline_false = comp_trust.get('false_executions', 0)
        current_false = trust.get('false_executions', 0)
        diff = current_false - baseline_false
        lines.append(f"| False Executions | {baseline_false} | {current_false} | {diff:+d} |")
        
        # Success rate
        baseline_success = comp_trust.get('success_rate', 0)
        current_success = trust.get('success_rate', 0)
        diff = current_success - baseline_success
        lines.append(f"| Success Rate | {baseline_success:.1f}% | {current_success:.1f}% | {diff:+.1f}% |")
        
        lines.append("")
    
    return "\n".join(lines)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate metrics report from session logs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument('--latest', action='store_true',
                        help='Use latest session metrics')
    parser.add_argument('--session', type=str,
                        help='Session ID (e.g., arm_20250114_153022)')
    parser.add_argument('--log-dir', type=str, default='logs',
                        help='Logs directory')
    parser.add_argument('--compare', type=str,
                        help='Path to baseline metrics JSON for comparison')
    parser.add_argument('--format', type=str, default='console',
                        help='Output format: console, markdown, json (comma-separated)')
    parser.add_argument('--output', type=str,
                        help='Output file path (for markdown/json)')
    
    args = parser.parse_args()
    
    log_dir = Path(args.log_dir)
    
    # Find metrics file
    if args.latest:
        metrics_path = find_latest_session(log_dir)
        if not metrics_path:
            print(f"Error: No metrics files found in {log_dir}")
            sys.exit(1)
        print(f"Using latest session: {metrics_path.stem}")
    elif args.session:
        metrics_path = log_dir / f"{args.session}_metrics.json"
        if not metrics_path.exists():
            print(f"Error: Metrics file not found: {metrics_path}")
            sys.exit(1)
    else:
        print("Error: Must specify --latest or --session")
        sys.exit(1)
    
    # Load metrics
    print(f"Loading metrics from: {metrics_path}")
    metrics = load_metrics(metrics_path)
    
    # Load comparison baseline if provided
    comparison = None
    if args.compare:
        comp_path = Path(args.compare)
        if not comp_path.exists():
            print(f"Warning: Comparison file not found: {comp_path}")
        else:
            print(f"Loading baseline from: {comp_path}")
            comparison = load_metrics(comp_path)
    
    # Parse formats
    formats = [f.strip() for f in args.format.split(',')]
    
    # Generate reports
    for fmt in formats:
        if fmt == 'console':
            report = generate_console_report(metrics, comparison)
            print("\n" + report + "\n")
        
        elif fmt == 'markdown':
            report = generate_markdown_report(metrics, comparison)
            
            if args.output:
                output_path = Path(args.output)
            else:
                output_path = log_dir / f"{metrics_path.stem}_report.md"
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(report)
            print(f"✓ Markdown report saved: {output_path}")
        
        elif fmt == 'json':
            if args.output:
                output_path = Path(args.output)
            else:
                output_path = log_dir / f"{metrics_path.stem}_report.json"
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(metrics, f, indent=2)
            print(f"✓ JSON report saved: {output_path}")
        
        else:
            print(f"Warning: Unknown format '{fmt}', skipping")


if __name__ == "__main__":
    main()





