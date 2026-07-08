"""The git-ls-files cwd hazard: a self-scan corpus built from a bare `git ls-files "*.py"`
mis-scopes by working directory (the monorepo has no per-faculty .git). tracked_py_files pins scope
with `git -C <root>`, so the corpus is identical regardless of cwd. Self-contained: the test builds
its OWN throwaway git repo (no dependence on the surrounding tree being a git repo)."""
import os
import subprocess

from makoto.tests._repo_scope import tracked_py_files


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _repo(tmp_path):
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "t@t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    return tmp_path


def test_tracked_py_files_pins_scope_to_the_given_root(tmp_path):
    r = _repo(tmp_path)
    (r / "faculty").mkdir()
    (r / "faculty" / "live.py").write_text("x = 1\n", encoding="utf-8")
    (r / "faculty" / "tests").mkdir()
    (r / "faculty" / "tests" / "test_x.py").write_text("y = 1\n", encoding="utf-8")
    (r / "other.py").write_text("z = 1\n", encoding="utf-8")   # sibling OUTSIDE the pinned root
    _git(["add", "-A"], r)
    _git(["commit", "-qm", "seed"], r)
    got = set(tracked_py_files(r / "faculty"))
    assert got == {"live.py"}     # only faculty/*.py, tests/ excluded, sibling never swept in


def test_scope_is_cwd_independent(tmp_path):
    r = _repo(tmp_path)
    (r / "faculty").mkdir()
    (r / "faculty" / "live.py").write_text("x = 1\n", encoding="utf-8")
    (r / "loud.py").write_text("z = 1\n", encoding="utf-8")    # a bare ls-files from r would add this
    _git(["add", "-A"], r)
    _git(["commit", "-qm", "seed"], r)
    baseline = set(tracked_py_files(r / "faculty"))
    here = os.getcwd()
    try:
        os.chdir(r)
        assert set(tracked_py_files(r / "faculty")) == baseline
        os.chdir(r / "faculty")
        assert set(tracked_py_files(r / "faculty")) == baseline
    finally:
        os.chdir(here)