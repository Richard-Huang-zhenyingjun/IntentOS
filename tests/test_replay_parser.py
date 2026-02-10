"""
Test replay tool parses events without crashing.
"""
import pytest
import json
import tempfile
from pathlib import Path
from src.tools.replay_events import format_event, replay


def test_format_known_events():
    """Known event types format without error"""
    events = [
        {'event_type': 'auth_token_issued', 'frame': 10, 'data': {
            'token_id': 'auth_abc123', 'scope': 'task_session', 'source': 'keyboard', 'quality': 1.0}},
        {'event_type': 'trust_updated', 'frame': 20, 'data': {
            'task_trust': 0.78, 'event': 'grasp_retry'}},
        {'event_type': 'trust_reauth_triggered', 'frame': 30, 'data': {
            'reason': 'trust_below_threshold', 'trust': 0.45}},
        {'event_type': 'task_completed', 'frame': 100, 'data': {
            'cleaned': 3, 'skipped': 1, 'failed': 0, 'success_rate': 0.75}},
    ]
    
    for event in events:
        line = format_event(event)
        assert isinstance(line, str)
        assert len(line) > 0


def test_format_unknown_event():
    """Unknown event types don't crash"""
    event = {'event_type': 'totally_unknown', 'frame': 5, 'data': {'foo': 'bar'}}
    line = format_event(event)
    assert 'totally_unknown' in line


def test_replay_file(tmp_path):
    """Replay tool processes a JSONL file without crashing"""
    events = [
        {'event_type': 'autonomy_level_set', 'frame': 0, 'data': {'level': 'A2_TASK_CONFIRM'}},
        {'event_type': 'auth_token_issued', 'frame': 10, 'data': {'token_id': 'auth_abc', 'scope': 'task_session', 'source': 'keyboard', 'quality': 1.0}},
        {'event_type': 'trust_updated', 'frame': 50, 'data': {'task_trust': 0.88, 'event': 'none'}},
        {'event_type': 'task_completed', 'frame': 200, 'data': {'cleaned': 3, 'skipped': 0, 'failed': 0, 'success_rate': 1.0}},
    ]
    
    filepath = tmp_path / "events.jsonl"
    with open(filepath, 'w') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')
    
    # Should not crash
    replay(str(filepath), verbose=True)


