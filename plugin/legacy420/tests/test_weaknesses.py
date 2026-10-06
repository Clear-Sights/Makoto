import os
import subprocess
import sys
from pathlib import Path


def test_weaknesses():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / 'mesh' / 'weaknesses.py')], capture_output=True,
                            text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    assert result.returncode == 0, result.stdout + result.stderr
