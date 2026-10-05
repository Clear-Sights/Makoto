"""Entry point: python3 -m skill_triggers <HookEvent>. Never blocks a tool call."""
import runpy
from pathlib import Path

try:
    runpy.run_path(str(Path(__file__).parent / 'hooks' / 'trigger.py'), run_name='__main__')
except BaseException:
    pass
