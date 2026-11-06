"""Build plugin directories for the corpus gate from `git show <base>:plugin/makoto2.py`.

    python3 eval/variants.py BASE_REF HEAD_REF OUTDIR

Writes OUTDIR/{base,v1,v2,v3,all}/makoto2.py (and the data file it reads):
  base = BASE_REF unchanged
  v1   = base without the MAKOTO_BLOCK_IN report-only scope
  v2   = base without the second-Stop cap
  v3   = base with infrastructure errors blocking instead of admitting
  all  = HEAD_REF (the three changes together)
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def show(ref, path):
    return subprocess.run(['git', '-C', str(REPO), 'show', f'{ref}:{path}'], capture_output=True, check=True).stdout.decode()


def replace(text, old, new):
    assert text.count(old) == 1, old[:80]
    return text.replace(old, new)


def v1(text):
    start = text.index("            scope = config.get('block_in')\n")
    end = text.index("            elif reason and event.get('stop_hook_active') and held_again(event, journal):")
    return text[:start] + "            if reason and event.get('stop_hook_active') and held_again(event, journal):" + text[end + len("            elif reason and event.get('stop_hook_active') and held_again(event, journal):"):]


def v2(text):
    return replace(text, "            elif reason and event.get('stop_hook_active') and held_again(event, journal):",
                   "            elif False:")


HELPER = '''
def infrastructure_block(raw, error):
    try:
        event = json.loads(raw)
    except ValueError:
        event = {}
    reason = 'makoto infrastructure error, step blocked: %s: %s. To disable Makoto run in a terminal: claude plugin disable makoto' % (type(error).__name__, error)
    return d_out(event if isinstance(event, dict) else {}, reason)

'''


def v3(text):
    text = replace(text, "        return {'systemMessage': 'makoto infrastructure error, step allowed: %s: %s' % (type(error).__name__, error)}\n\n\n# ====",
                   "        return infrastructure_block(raw, error)\n\n\n# ====")
    text = replace(text, "\ndef d_out(event, reason):", HELPER + "\ndef d_out(event, reason):")
    return text


def main():
    base_ref, head_ref, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    base = show(base_ref, 'plugin/makoto2.py')
    data = show(base_ref, 'plugin/common-english.txt')
    for name, text in (('base', base), ('v1', v1(base)), ('v2', v2(base)), ('v3', v3(base)),
                       ('all', show(head_ref, 'plugin/makoto2.py'))):
        (out / name).mkdir(parents=True, exist_ok=True)
        (out / name / 'makoto2.py').write_text(text)
        (out / name / 'common-english.txt').write_text(data)
        compile(text, name, 'exec')


if __name__ == '__main__':
    main()
