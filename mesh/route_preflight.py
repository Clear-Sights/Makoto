"""Prove Tiller's check/plant/check contract in disposable working trees."""
from pathlib import Path
import shutil
import subprocess
import tempfile
from plants import local_copy, read, ROOT


def prove():
    failures = []
    _, rows = read(ROOT / 'MESH.tsv')
    for row in rows:
        copy = local_copy()
        try:
            # Same marker contract as route.sh; every command runs in the copy.
            with tempfile.TemporaryDirectory(prefix='makoto-preflight-') as parent:
                parent = Path(parent)
                (parent / '.mesh-preflight-disposable').touch()
                target = parent / 'repo'
                shutil.move(str(copy), target)
                results = [subprocess.run(cmd, shell=True, cwd=target,
                           capture_output=True, text=True)
                           for cmd in (row['check'], row['plant'], row['check'])]
                ok = [r.returncode == 0 for r in results] == [True, True, False]
                if not ok:
                    failures.append(row['hole'])
                    for result in results:
                        print(result.stdout + result.stderr)
                print('route ' + row['hole'] + ': ' + ('PASS' if ok else 'FAIL'))
        finally:
            if copy.exists(): shutil.rmtree(copy)
    return failures


if __name__ == '__main__':
    raise SystemExit(bool(prove()))
