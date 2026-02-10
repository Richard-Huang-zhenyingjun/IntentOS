"""
Export trust timeline from events.jsonl to CSV for plotting.

Usage:
    python -m src.tools.export_trust_csv runs/.../events.jsonl -o trust.csv
"""
import csv
import json
import sys
from pathlib import Path


def export_trust_csv(events_path: str, output_path: str = "trust_timeline.csv"):
    events = []
    with open(events_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'frame', 'event_type', 'task_trust', 'error_code',
            'token_id', 'autonomy_level',
        ])
        
        current_trust = 1.0
        current_token = None
        current_autonomy = None
        
        for event in events:
            etype = event.get('event_type', '')
            frame = event.get('frame', 0)
            data = event.get('data', {})
            
            if etype == 'trust_updated':
                current_trust = data.get('task_trust', current_trust)
                current_token = data.get('token_id', current_token)
            elif etype == 'auth_token_issued':
                current_token = data.get('token_id')
            elif etype == 'autonomy_level_set':
                current_autonomy = data.get('level')
            
            if etype in ('trust_updated', 'trust_reauth_triggered',
                         'auth_token_issued', 'auth_token_invalidated',
                         'task_completed', 'object_completed', 'error_occurred'):
                writer.writerow([
                    frame, etype, f"{current_trust:.4f}",
                    data.get('event', data.get('error_code', '')),
                    current_token or '',
                    current_autonomy or '',
                ])
    
    print(f"Exported trust timeline to {output_path}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python -m src.tools.export_trust_csv <events.jsonl> [-o output.csv]")
        sys.exit(1)
    
    events_path = sys.argv[1]
    
    # Parse output path
    if '-o' in sys.argv:
        o_index = sys.argv.index('-o')
        if o_index + 1 < len(sys.argv):
            output = sys.argv[o_index + 1]
        else:
            print("Error: -o flag requires an output file path")
            sys.exit(1)
    else:
        output = 'trust_timeline.csv'
    
    export_trust_csv(events_path, output)

