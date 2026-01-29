#!/usr/bin/env python3
"""
Generate Metrics Report (Week 9)

Produces comprehensive trust and performance report.
Proves safety guarantees quantitatively.

Usage:
    python scripts/generate_metrics_report.py
    python scripts/generate_metrics_report.py --format html
    python scripts/generate_metrics_report.py --output report.txt
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from intent_core.metrics_collector import SessionMetrics


def generate_report(metrics: SessionMetrics, format: str = 'text') -> str:
    """
    Generate comprehensive metrics report
    
    Sections:
    1. Safety Guarantees (CRITICAL)
    2. Trust Metrics
    3. Execution Flow
    4. Robustness
    5. Performance
    
    Args:
        metrics: SessionMetrics from MetricsCollector
        format: Output format ('text' or 'html')
        
    Returns:
        Formatted report string
    """
    
    if format == 'html':
        return _generate_html_report(metrics)
    else:
        return _generate_text_report(metrics)


def _generate_text_report(metrics: SessionMetrics) -> str:
    """Generate text-based report"""
    report = []
    
    # === HEADER ===
    report.append("=" * 70)
    report.append("INTENT INTERFACE SYSTEM METRICS REPORT")
    report.append("=" * 70)
    report.append("")
    
    # Session info
    report.append(f"Session ID: {metrics.session_id}")
    report.append(f"Start Time: {datetime.fromtimestamp(metrics.start_time).strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Duration: {metrics.duration_seconds:.1f}s")
    report.append(f"Total Frames: {metrics.total_frames}")
    report.append("")
    
    # === SECTION 1: SAFETY GUARANTEES (CRITICAL) ===
    report.append("=" * 70)
    report.append("1. SAFETY GUARANTEES (CRITICAL)")
    report.append("=" * 70)
    report.append("")
    
    # False executions check
    if metrics.false_executions == 0:
        report.append("✓ false_executions = 0 (PASS)")
    else:
        report.append(f"✗ false_executions = {metrics.false_executions} (FAIL - CRITICAL VIOLATION)")
    
    # Unauthorized executions check
    if metrics.unauthorized_executions == 0:
        report.append("✓ unauthorized_executions = 0 (PASS)")
    else:
        report.append(f"✗ unauthorized_executions = {metrics.unauthorized_executions} (FAIL - CRITICAL VIOLATION)")
    
    report.append("")
    
    if metrics.false_executions == 0 and metrics.unauthorized_executions == 0:
        report.append("🎉 ALL SAFETY GUARANTEES MET 🎉")
    else:
        report.append("⚠️ SAFETY VIOLATIONS DETECTED ⚠️")
    
    report.append("")
    
    # === SECTION 2: TRUST METRICS ===
    report.append("=" * 70)
    report.append("2. TRUST METRICS")
    report.append("=" * 70)
    report.append("")
    
    # Ambiguity handling
    report.append(f"Ambiguity Waits: {metrics.ambiguity_waits}")
    report.append("  → System waited for clarity instead of guessing")
    report.append("")
    
    # Pause/recovery
    report.append(f"Pause Triggers: {metrics.pause_triggers}")
    if metrics.pause_triggers > 0:
        report.append("  Breakdown:")
        for trigger, count in metrics.pause_trigger_types.items():
            report.append(f"    - {trigger}: {count}")
    report.append("  → System paused safely when failures detected")
    report.append("")
    
    report.append(f"Recovery Completions: {metrics.recovery_completions}")
    recovery_rate = (metrics.recovery_completions / max(1, metrics.pause_triggers)) * 100
    report.append(f"  → {recovery_rate:.0f}% of pauses recovered successfully")
    report.append("")
    
    # Oscillation handling
    report.append(f"Oscillation Events: {metrics.oscillation_events}")
    report.append("  → System suppressed rapid attention switching")
    report.append("")
    
    # === SECTION 3: EXECUTION FLOW ===
    report.append("=" * 70)
    report.append("3. EXECUTION FLOW")
    report.append("=" * 70)
    report.append("")
    
    # Scope
    report.append(f"Scope Acquisitions: {metrics.scope_acquisitions}")
    report.append(f"Scope Losses: {metrics.scope_losses}")
    report.append(f"Scope Changes: {metrics.scope_changes}")
    report.append("")
    
    # Affordances
    report.append(f"Affordances Generated: {metrics.affordances_generated}")
    report.append(f"  - State-aware: {metrics.state_aware_affordances}")
    report.append(f"  - Fallback: {metrics.fallback_affordances}")
    if metrics.affordances_generated > 0:
        state_aware_rate = (metrics.state_aware_affordances / metrics.affordances_generated) * 100
        report.append(f"  → {state_aware_rate:.0f}% were state-aware (intelligent)")
    report.append(f"Affordances Blocked: {metrics.affordances_blocked}")
    report.append("")
    
    # Confirmation
    report.append(f"Confirmation Attempts: {metrics.confirmation_attempts}")
    report.append(f"Confirmation Successes: {metrics.confirmation_successes}")
    report.append(f"Confirmation Cancellations: {metrics.confirmation_cancellations}")
    if metrics.confirmation_attempts > 0:
        conf_rate = (metrics.confirmation_successes / metrics.confirmation_attempts) * 100
        report.append(f"  → {conf_rate:.0f}% confirmation rate")
    report.append("")
    
    # Execution
    report.append(f"Execution Requests: {metrics.execution_requests}")
    report.append(f"Execution Successes: {metrics.execution_successes}")
    report.append(f"Execution Refusals: {metrics.execution_refusals}")
    if metrics.execution_requests > 0:
        exec_rate = (metrics.execution_successes / metrics.execution_requests) * 100
        report.append(f"  → {exec_rate:.0f}% execution rate")
    
    if metrics.execution_refusals > 0 and metrics.refusal_reasons:
        report.append("  Refusal Breakdown:")
        for reason, count in sorted(metrics.refusal_reasons.items(), key=lambda x: -x[1]):
            report.append(f"    - {reason}: {count}")
    report.append("")
    
    # Undo
    report.append(f"Undo Requests: {metrics.undo_requests}")
    report.append(f"Undo Successes: {metrics.undo_successes}")
    report.append(f"Undo Refusals: {metrics.undo_refusals}")
    report.append(f"Undo Expirations: {metrics.undo_expirations}")
    if metrics.undo_requests > 0:
        undo_rate = (metrics.undo_successes / metrics.undo_requests) * 100
        report.append(f"  → {undo_rate:.0f}% undo success rate")
    report.append("")
    
    # === SECTION 4: ROBUSTNESS ===
    report.append("=" * 70)
    report.append("4. ROBUSTNESS")
    report.append("=" * 70)
    report.append("")
    
    report.append(f"Max Objects Tracked: {metrics.max_tracked_objects}")
    report.append(f"Avg Objects Tracked: {metrics.avg_tracked_objects:.1f}")
    report.append("  → Multi-object handling capability")
    report.append("")
    
    # Calculate key ratios
    decisions_made = metrics.execution_successes
    decisions_refused = metrics.execution_refusals + metrics.ambiguity_waits + metrics.pause_triggers
    total_decision_points = decisions_made + decisions_refused
    
    if total_decision_points > 0:
        safe_refusal_rate = (decisions_refused / total_decision_points) * 100
        report.append(f"Total Decision Points: {total_decision_points}")
        report.append(f"  - Actions Taken: {decisions_made}")
        report.append(f"  - Safe Refusals: {decisions_refused}")
        report.append(f"  → {safe_refusal_rate:.0f}% refusal rate (safety-first approach)")
    report.append("")
    
    # === SECTION 5: PERFORMANCE ===
    report.append("=" * 70)
    report.append("5. PERFORMANCE")
    report.append("=" * 70)
    report.append("")
    
    report.append(f"Average Frame Time: {metrics.avg_frame_time_ms:.2f}ms")
    report.append(f"Max Frame Time: {metrics.max_frame_time_ms:.2f}ms")
    
    fps = 1000 / metrics.avg_frame_time_ms if metrics.avg_frame_time_ms > 0 else 0
    report.append(f"Effective FPS: {fps:.1f}")
    
    if fps >= 25:
        report.append("  → Real-time performance achieved")
    elif fps >= 15:
        report.append("  → Acceptable performance for interactive use")
    else:
        report.append("  → Performance optimization recommended")
    
    report.append("")
    
    # === FOOTER ===
    report.append("=" * 70)
    report.append("END OF REPORT")
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 70)
    
    return "\n".join(report)


def _generate_html_report(metrics: SessionMetrics) -> str:
    """Generate HTML-based report"""
    html = []
    
    html.append("<!DOCTYPE html>")
    html.append("<html><head>")
    html.append("<title>Intent Interface Metrics Report</title>")
    html.append("<style>")
    html.append("body { font-family: Arial, sans-serif; margin: 40px; background: #1e1e1e; color: #d4d4d4; }")
    html.append("h1 { color: #569cd6; border-bottom: 2px solid #569cd6; padding-bottom: 10px; }")
    html.append("h2 { color: #4ec9b0; margin-top: 30px; }")
    html.append(".metric { margin: 10px 0; padding: 10px; background: #2d2d2d; border-left: 3px solid #4ec9b0; }")
    html.append(".critical { border-left-color: #f48771; }")
    html.append(".success { color: #4ec9b0; }")
    html.append(".failure { color: #f48771; }")
    html.append(".section { margin: 20px 0; padding: 20px; background: #252526; border-radius: 5px; }")
    html.append("</style>")
    html.append("</head><body>")
    
    html.append("<h1>Intent Interface System Metrics Report</h1>")
    html.append(f"<p><strong>Session:</strong> {metrics.session_id}</p>")
    html.append(f"<p><strong>Duration:</strong> {metrics.duration_seconds:.1f}s | <strong>Frames:</strong> {metrics.total_frames}</p>")
    
    # Safety section
    html.append("<div class='section'>")
    html.append("<h2>1. Safety Guarantees (CRITICAL)</h2>")
    
    if metrics.false_executions == 0:
        html.append("<div class='metric success'>✓ false_executions = 0 (PASS)</div>")
    else:
        html.append(f"<div class='metric critical failure'>✗ false_executions = {metrics.false_executions} (FAIL)</div>")
    
    if metrics.unauthorized_executions == 0:
        html.append("<div class='metric success'>✓ unauthorized_executions = 0 (PASS)</div>")
    else:
        html.append(f"<div class='metric critical failure'>✗ unauthorized_executions = {metrics.unauthorized_executions} (FAIL)</div>")
    
    html.append("</div>")
    
    # Trust section
    html.append("<div class='section'>")
    html.append("<h2>2. Trust Metrics</h2>")
    html.append(f"<div class='metric'>Ambiguity Waits: <strong>{metrics.ambiguity_waits}</strong></div>")
    html.append(f"<div class='metric'>Pause Triggers: <strong>{metrics.pause_triggers}</strong></div>")
    html.append(f"<div class='metric'>Recoveries: <strong>{metrics.recovery_completions}</strong></div>")
    html.append("</div>")
    
    # Execution section
    html.append("<div class='section'>")
    html.append("<h2>3. Execution Flow</h2>")
    html.append(f"<div class='metric'>Executions: <strong>{metrics.execution_successes}</strong></div>")
    html.append(f"<div class='metric'>Refusals: <strong>{metrics.execution_refusals}</strong></div>")
    html.append(f"<div class='metric'>Undos: <strong>{metrics.undo_successes}</strong></div>")
    html.append("</div>")
    
    html.append("</body></html>")
    
    return "\n".join(html)


def print_summary(metrics: SessionMetrics):
    """Print condensed summary"""
    print("\n" + "=" * 50)
    print("METRICS SUMMARY")
    print("=" * 50)
    
    # Safety
    print("\nSafety:")
    safety_status = "✓ PASS" if metrics.false_executions == 0 and metrics.unauthorized_executions == 0 else "✗ FAIL"
    print(f"  {safety_status}")
    print(f"    false_executions = {metrics.false_executions}")
    print(f"    unauthorized_executions = {metrics.unauthorized_executions}")
    
    # Trust
    print("\nTrust:")
    print(f"  ambiguity_waits = {metrics.ambiguity_waits}")
    print(f"  pause_triggers = {metrics.pause_triggers}")
    print(f"  recovery_completions = {metrics.recovery_completions}")
    
    # Execution
    print("\nExecution:")
    print(f"  executions = {metrics.execution_successes}")
    print(f"  refusals = {metrics.execution_refusals}")
    print(f"  undos = {metrics.undo_successes}")
    
    # Performance
    print("\nPerformance:")
    print(f"  avg_frame_time = {metrics.avg_frame_time_ms:.2f}ms")
    fps = 1000 / metrics.avg_frame_time_ms if metrics.avg_frame_time_ms > 0 else 0
    print(f"  effective_fps = {fps:.1f}")
    
    print("\n" + "=" * 50 + "\n")


def print_comparison(metrics_list: list[SessionMetrics]):
    """
    Print comparison of multiple sessions
    
    Args:
        metrics_list: List of SessionMetrics to compare
    """
    print("\n" + "=" * 70)
    print("METRICS COMPARISON")
    print("=" * 70)
    
    print(f"\n{'Session ID':<20} {'Duration':<12} {'Executions':<12} {'Refusals':<12} {'Safety':<10}")
    print("-" * 70)
    
    for m in metrics_list:
        session_short = m.session_id[-8:]
        duration_str = f"{m.duration_seconds:.1f}s"
        safety_str = "✓" if m.false_executions == 0 and m.unauthorized_executions == 0 else "✗"
        
        print(f"{session_short:<20} {duration_str:<12} {m.execution_successes:<12} {m.execution_refusals:<12} {safety_str:<10}")
    
    print("=" * 70 + "\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Generate Intent Interface Metrics Report',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--format',
        choices=['text', 'html'],
        default='text',
        help='Output format (default: text)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output file path (default: metrics_report.txt)'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Print summary only (no full report)'
    )
    
    args = parser.parse_args()
    
    # Example usage with mock data
    print("Generating example metrics report...\n")
    
    from intent_core.metrics_collector import MetricsCollector
    import time
    
    collector = MetricsCollector()
    
    # Simulate some activity
    print("Simulating session activity...")
    for i in range(10):
        time.sleep(0.01)
        collector.frame_times.append(10.0 + i * 0.5)
    
    # Simulate metrics
    collector.scope_acquisitions = 5
    collector.scope_losses = 2
    collector.affordances_generated = 10
    collector.state_aware_affordances = 8
    collector.fallback_affordances = 2
    collector.confirmation_attempts = 7
    collector.confirmation_successes = 5
    collector.execution_requests = 5
    collector.execution_successes = 4
    collector.execution_refusals = 1
    collector.refusal_reasons = {'ambiguity': 1}
    collector.undo_requests = 2
    collector.undo_successes = 2
    collector.ambiguity_waits = 3
    collector.pause_triggers = 1
    collector.pause_trigger_types = {'hand_loss': 1}
    collector.recovery_completions = 1
    collector.max_tracked_objects = 3
    collector.total_tracked_objects = 25
    collector.tracked_object_samples = 10
    
    metrics = collector.get_session_metrics()
    
    if args.summary:
        # Print summary only
        print_summary(metrics)
    else:
        # Generate full report
        report = generate_report(metrics, format=args.format)
        print(report)
        
        # Save to file
        if args.output:
            output_path = args.output
        else:
            ext = '.html' if args.format == 'html' else '.txt'
            output_path = Path(f"metrics_report{ext}")
        
        output_path.write_text(report)
        print(f"\nReport saved to: {output_path}")
        
        # Also print summary
        print_summary(metrics)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
