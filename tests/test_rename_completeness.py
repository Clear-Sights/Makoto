"""Rename-completeness gate: after the Pre-Check / Stop-Check taxonomy rename (the close-check tier
later folded into Stop, 2026-06-11), NO residual old taxonomy name (Gate / Pattern / load_gates /
load_patterns / run_stop_gates / makoto.gates / makoto.predicates) survives anywhere in the .py tree
— GateContext is the ONE intentional keep (the shared Stop-event substrate name), so it is excluded
from the \bGate\b sweep. (The folded-away closechecks/postchecks packages are pinned dead by
tests/test_check_taxonomy.py's ImportError assertions.)"""
import subprocess
from pathlib import Path
ROOT = Path(__file__).parent.parent


def _grep(pattern):
    r = subprocess.run(["grep", "-rnE", pattern, "--include=*.py", str(ROOT)],
                       capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if "__pycache__" not in l]


def _is_real_offender(line: str) -> bool:
    """A grep hit is a real residual UNLESS it is a sanctioned non-taxonomy symbol. These exclusions
    name DIFFERENT symbols that merely share spelling — narrowing the sweep to the renamed taxonomy,
    not weakening it (the same role GateContext plays in the plan's own exclusion):
      - GateContext      : the ONE intentional taxonomy keep (shared Stop-event substrate name).
      - re.Pattern / re.Gate : the Python STDLIB compiled-regex type (`re.Pattern`) — never makoto's
                           old `Pattern`/`Gate` dataclass; it is a stdlib symbol the rename must not touch.
      - this gate file   : the completeness gate must spell the forbidden tokens to forbid them.
    """
    if "GateContext" in line:
        return False
    if "re.Pattern" in line or "re.Gate" in line:   # makoto-allow: stdlib re.Pattern type, not makoto's renamed Pattern dataclass
        return False
    if "test_rename_completeness.py" in line:        # makoto-allow: the gate names the tokens it forbids
        return False
    return True


def test_no_residual_old_taxonomy_names():
    offenders = [l for l in _grep(r'\bGate\b|\bPattern\b|load_gates|load_patterns|run_stop_gates'
                                  r'|makoto\.gates|makoto\.predicates')
                 if _is_real_offender(l)]
    assert offenders == [], "residual old taxonomy names:\n" + "\n".join(offenders)


def test_no_old_dirs():
    assert not (ROOT / "gates").exists() and not (ROOT / "predicates").exists()
