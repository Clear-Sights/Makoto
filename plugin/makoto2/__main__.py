"""Live entry: python -m makoto2, one serialized native event on stdin."""
import json
import os
import sys
from pathlib import Path
from .hook import main


def run():
    cfg = json.loads(Path(__file__).with_name('config.json').read_text(encoding='utf-8'))
    cfg['state_dir'] = os.path.expanduser(os.environ.get('MAKOTO_STATE_DIR', cfg['state_dir']))
    cfg['adapter'] = os.environ.get('MAKOTO_ADAPTER', cfg['adapter'])
    scope = os.environ.get('MAKOTO_BLOCK_IN')
    if scope:
        cfg['block_in'] = [p for p in scope.split(os.pathsep) if p]
    sys.stdout.write(json.dumps(main(sys.stdin.read(), cfg)))
    return 0


if __name__ == '__main__':
    sys.exit(run())
