"""The liveness gate enforces only on CLOSED units in the working project. A touched .py
under the session cwd fires (this is how pytest tmp fixtures and real project files appear); a
touched .py living in a temp/scratch root OUTSIDE the cwd (e.g. /tmp/mining/*, the live-session
contamination vector) is skipped. This realizes the user's "a block counts only when opened AND
closed" criterion at the unit-closure layer WITHOUT weakening the analyzer: detection logic is
unchanged, only the firing scope narrows to closed work. Suppression is limited to known scratch
roots — never a blanket skip — so the gate keeps its teeth on all real code."""
from makoto.stopchecks import stopcheck_liveness as CL

DEAD = "def fn():\n d = 1 + 1\n return 0\n"   # exactly one genuinely-illusory statement


class _Ctx:
    def __init__(self, cwd, touched, src=DEAD):
        self.cwd = cwd
        self.touched = list(touched)
        self._src = src

    def fs_read(self, p):                    # avoids disk: every touched path reads as DEAD
        return self._src


def test_scratch_py_outside_cwd_is_skipped(tmp_path):
    # cwd is a real project; the touched file is stray /tmp scratch OUTSIDE it -> not a closed unit.
    ctx = _Ctx(cwd=str(tmp_path), touched=["/tmp/mining/dropped_ask_miner.py"])
    assert CL._run(ctx) == [], "stray /tmp scratch outside the working dir must not fire"


def test_dead_code_inside_cwd_fires_even_under_tmp(tmp_path):
    # The SAME dead code, but INSIDE the working dir (pytest tmp_path is itself under a temp root,
    # yet must still fire) -> a closed unit under construction -> the analyzer's teeth are intact.
    f = tmp_path / "dead.py"
    ctx = _Ctx(cwd=str(tmp_path), touched=[str(f)])
    out = CL._run(ctx)
    assert len(out) == 1 and out[0].pattern_id == "gate.liveness", \
        "dead code in the working dir must fire even though pytest tmp lives under a temp root"


def test_suppression_is_scratch_only_not_a_blanket(tmp_path):
    # Invariant: only KNOWN scratch roots are ever suppressed. A non-temp path with no cwd still
    # fires -> the scope filter can never silently swallow real code.
    ctx = _Ctx(cwd=None, touched=["/home/dev/project/dead.py"])
    assert len(CL._run(ctx)) == 1, "a non-scratch path must fire; suppression is scratch-root-only"
