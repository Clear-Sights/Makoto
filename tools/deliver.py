#!/usr/bin/env python3
"""Host interception example: proposed Stop JSON on stdin, final bytes only if paid.

MAKOTO_STATE_DIR and MAKOTO_ADAPTER are the same settings as the live hooks.
This wrapper owns stdout delivery; it does not install an interception in Claude.
"""
import json
import os
from pathlib import Path
import sys
from run_pairs import invoke, held


def main():
    event = json.load(sys.stdin)
    event['hook_event_name'] = 'Stop'
    response = invoke(event, Path(os.environ['MAKOTO_STATE_DIR']), os.environ.get('MAKOTO_ADAPTER', 'inferred'))
    if held(response):
        print(json.dumps(response), file=sys.stderr)
        return 2
    sys.stdout.write(event.get('last_assistant_message', ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
