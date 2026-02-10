"""
Replay tool: reads events.jsonl → human-readable timeline.

Usage:
    python -m src.tools.replay_events runs/20250101_120000/events.jsonl
"""
import json
import sys
from pathlib import Path
from typing import List


# Event display formatters
FORMATTERS = {
    'auth_token_issued': lambda d: (
        f"🔑 AUTH ISSUED: {d.get('token_id', '?')[:16]} "
        f"(scope={d.get('scope')}, source={d.get('source')}, "
        f"quality={d.get('quality', 0):.2f})"
    ),
    'auth_token_completed': lambda d: (
        f"✅ AUTH COMPLETED: {d.get('token_id', '?')[:16]} "
        f"(trust={d.get('final_trust', 0):.3f})"
    ),
    'auth_token_invalidated': lambda d: (
        f"🚫 AUTH INVALIDATED: {d.get('token_id', '?')[:16]} "
        f"(reason={d.get('reason', '?')})"
    ),
    'trust_updated': lambda d: (
        f"📊 TRUST: {d.get('task_trust', 0):.3f} "
        f"(event={d.get('event', '?')})"
    ),
    'trust_reauth_triggered': lambda d: (
        f"⚠️  RE-AUTH TRIGGERED: {d.get('reason', '?')} "
        f"(trust={d.get('trust', 0):.3f})"
    ),
    'safe_pause_started': lambda d: (
        f"⏸️  SAFE PAUSE: {d.get('n_primitives', 0)} primitives "
        f"(grasping={d.get('is_grasping', False)})"
    ),
    'safe_pause_completed': lambda d: "⏸️  SAFE PAUSE COMPLETE",
    'proposal_created': lambda d: (
        f"💡 PROPOSAL: {d.get('action', '?')} "
        f"(source={d.get('source', '?')}, confidence={d.get('confidence', 0):.2f})"
    ),
    'confirm_received': lambda d: (
        f"👍 CONFIRMED: {d.get('action', '?')} (source={d.get('source', '?')})"
    ),
    'task_completed': lambda d: (
        f"🏁 TASK DONE: cleaned={d.get('cleaned', 0)}, "
        f"skipped={d.get('skipped', 0)}, failed={d.get('failed', 0)}, "
        f"rate={d.get('success_rate', 0):.0%}"
    ),
    'primitive_completed': lambda d: (
        f"  ⚙️  Primitive: {d.get('type', '?')} → {d.get('status', '?')}"
    ),
    'object_started': lambda d: (
        f"📦 Object {d.get('object_id', '?')} started"
    ),
    'object_completed': lambda d: (
        f"📦 Object {d.get('object_id', '?')} → {d.get('status', '?')}"
    ),
    'error_occurred': lambda d: (
        f"  ❌ ERROR: {d.get('error_code', '?')} ({d.get('detail', '')})"
    ),
    'autonomy_level_set': lambda d: (
        f"🎚️  AUTONOMY: {d.get('level', '?')}"
    ),
    'autonomy_object_await_confirm': lambda d: (
        f"⏳ AWAITING OBJECT CONFIRM ({d.get('objects_remaining', '?')} remaining)"
    ),
}


def format_event(event: dict) -> str:
    """Format a single event for display"""
    event_type = event.get('event_type', event.get('type', 'unknown'))
    frame = event.get('frame', 0)
    data = event.get('data', {})
    
    formatter = FORMATTERS.get(event_type)
    if formatter:
        detail = formatter(data)
    else:
        detail = f"{event_type}: {json.dumps(data, default=str)[:120]}"
    
    return f"[F{frame:>6}] {detail}"


def replay(filepath: str, verbose: bool = False):
    """Replay events from JSONL file"""
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}")
        return
    
    events = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    
    print(f"═══ Replay: {filepath} ({len(events)} events) ═══\n")
    
    # Summary stats
    trust_events = [e for e in events if e.get('event_type') == 'trust_updated']
    auth_events = [e for e in events if 'auth_token' in e.get('event_type', '')]
    reauth_events = [e for e in events if e.get('event_type') == 'trust_reauth_triggered']
    
    print(f"Auth tokens issued: {sum(1 for e in auth_events if 'issued' in e.get('event_type', ''))}")
    print(f"Re-auth events: {len(reauth_events)}")
    if trust_events:
        final_trust = trust_events[-1].get('data', {}).get('task_trust', '?')
        print(f"Final trust: {final_trust}")
    print()
    
    # Timeline
    skip_types = set() if verbose else {'trust_updated'}  # Skip frequent trust updates unless verbose
    
    for event in events:
        event_type = event.get('event_type', '')
        if not verbose and event_type in skip_types:
            continue
        print(format_event(event))
    
    print(f"\n═══ End of replay ═══")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m src.tools.replay_events <events.jsonl> [--verbose]")
        sys.exit(1)
    
    filepath = sys.argv[1]
    verbose = '--verbose' in sys.argv
    replay(filepath, verbose)


if __name__ == '__main__':
    main()


