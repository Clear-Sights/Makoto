"""Direct predicate-level battery for makoto.substrate._canonAtoms.atom_destructive_command /
_DESTRUCTIVE_RX -- the denylist regex behind THE_CANON_17's destructive_command literal (which
gates BLOCK_IDS nosrc_destruct/notestedit_destruct). Complements test_canon_fingerprints.py's
_DESTRUCTIVE_ROW fixture, which only ever exercises "rm -rf build/"; this file is the one place
that exercises the regex's individual denylist entries across both polarities.

Origin: GitHub issue #10 found `dd if=` firing on a read-only `dd` (no `of=`) and missing a write
where `of=` precedes `if=`. Auditing the other 8 denylist entries for the same two shapes -- (a) a
condition that gates real destructiveness but isn't checked, (b) a match that only looks at the
token immediately following the base command instead of anywhere in it -- surfaced the same shapes
in `git clean` (dry-run `-n` ignored), `git push` (force required to be the very next token,
dry-run ignored), `git reset --hard` (`--hard` required to be the very next token), and
`git checkout -- .` (a stray trailing `\b` after a non-word "." meant this entry could never fire
at all, since a bare "." argument is always followed by whitespace/EOL/punctuation, never a word
character). `mkfs.*` was investigated and deliberately left unchanged: its own `-n` means "dry
run" for mkfs.ext4 but "volume label" for mkfs.vfat, so a blanket dry-run exclusion would silently
create a false negative on a real mkfs.vfat format. `rm`'s long-form gap (`rm --recursive --force`)
is an explicit compatibility scope cut; the structured argv predicate closes the split-short-option
gap (`rm -r -f`) but keeps the documented long-form boundary.
"""
from __future__ import annotations

from makoto.substrate._canonAtoms import atom_check_disabled, atom_destructive_command


def _call(cmd):
    return {"name": "Bash", "input": {"command": cmd}, "result": {}}


def _fires(cmd):
    return atom_destructive_command([_call(cmd)], "")


def _disables(cmd):
    return atom_check_disabled([_call(cmd)], "")


# ---- dd: the issue's own matrix ----------------------------------------------------------------
def test_dd_if_and_of_fires():
    assert _fires("dd if=/dev/zero of=/dev/sda bs=1m")


def test_dd_of_before_if_fires():
    assert _fires("dd of=out.bin if=in.bin")


def test_dd_bare_if_no_of_is_a_read_and_does_not_fire():
    assert not _fires("dd if=big.txt bs=1 skip=101800 count=9500 2>/dev/null | fold -s -w 110")


def test_dd_read_piped_to_xxd_does_not_fire():
    assert not _fires("dd if=/dev/urandom bs=1 count=16 | xxd")


def test_dd_of_on_the_far_side_of_a_pipe_still_fires_via_that_dd():
    assert _fires("dd if=a.img | ssh host 'dd of=b.img'")


def test_of_mentioned_after_a_semicolon_in_an_unrelated_command_does_not_fire():
    assert not _fires("cat add.txt; echo of=x")


# ---- git clean: dry-run (-n/--dry-run) must veto a force/d/x match -----------------------------
def test_clean_force_and_d_fires():
    assert _fires("git clean -fd")


def test_clean_long_force_fires():
    assert _fires("git clean --force")


def test_clean_flag_before_force_still_fires():
    assert _fires("git clean -v -fd")


def test_clean_dry_run_short_combined_with_d_does_not_fire():
    assert not _fires("git clean -nd")


def test_clean_long_dry_run_before_force_does_not_fire():
    assert not _fires("git clean --dry-run -fd")


def test_clean_dry_run_after_force_does_not_fire():
    assert not _fires("git clean -fd --dry-run")


# ---- git push: force may appear anywhere; dry-run (-n/--dry-run) must veto ---------------------
def test_push_force_first_fires():
    assert _fires("git push -f origin main")


def test_push_force_at_end_fires():
    assert _fires("git push origin main --force")


def test_push_force_with_lease_does_not_fire():
    assert not _fires("git push --force-with-lease origin main")


def test_push_force_with_lease_equals_does_not_fire():
    assert not _fires("git push --force-with-lease=refs/heads/main:abc123 origin main")


def test_push_force_if_includes_and_force_with_lease_do_not_fire():
    assert not _fires("git push --force-if-includes --force-with-lease origin main")


def test_check_disabled_does_not_fire_for_force_with_lease_only_shape():
    assert not _disables("git push --force-with-lease origin main")


def test_check_disabled_does_not_fire_for_force_if_includes_only_shape():
    assert not _disables("git push --force-if-includes origin main")


def test_push_bare_long_force_still_fires():
    assert _fires("git push --force")


def test_push_bare_short_force_still_fires():
    assert _fires("git push -f")


def test_push_no_force_does_not_fire():
    assert not _fires("git push origin main")


def test_push_force_with_dry_run_does_not_fire_regardless_of_order():
    assert not _fires("git push --force --dry-run origin main")
    assert not _fires("git push --dry-run --force origin main")


def test_push_dry_run_in_a_later_chained_command_does_not_suppress_a_real_force_push():
    assert _fires("git push -f origin main && echo -n done")


# ---- git reset --hard: --hard may appear anywhere after `reset` --------------------------------
def test_reset_hard_after_another_flag_fires():
    assert _fires("git reset --quiet --hard")


def test_reset_soft_does_not_fire():
    assert not _fires("git reset --soft HEAD~1")


def test_reset_hard_in_a_later_chained_command_does_not_leak_into_an_unrelated_reset():
    assert not _fires("git reset --soft HEAD~1 && echo --hard-not-real")


# ---- git checkout -- . : was dead code (trailing \b after a non-word ".") ----------------------
def test_checkout_dash_dash_dot_fires():
    assert _fires("git checkout -- .")


def test_checkout_dash_dash_dot_followed_by_semicolon_fires():
    assert _fires("git checkout -- .; echo done")


def test_checkout_dash_dash_dot_prefixed_path_does_not_fire():
    assert not _fires("git checkout -- .foo")


# ---- untouched entries: regression pins ---------------------------------------------------------
def test_rm_rf_still_fires():
    assert _fires("rm -rf ./build")


def test_drop_table_still_fires_case_insensitively():
    assert _fires("DROP TABLE users")


def test_mkfs_dry_run_still_fires_because_of_vfat_label_ambiguity():
    assert _fires("mkfs.vfat -n USBDRIVE /dev/sdb1")


def test_unrelated_safe_command_does_not_fire():
    assert not _fires("git status")


# ---- disable denylist / shared argv normalizer -------------------------------------------------
def test_dd_lowercase_skip_does_not_disable_checks():
    assert not _disables("dd if=a bs=1 skip=1000 count=10")
    assert not _disables("dd if=a of=b skip=10")


def test_uppercase_skip_assignment_still_disables_checks():
    assert _disables("SKIP=slow pytest")
    assert _disables("SKIP=1 make test")


def test_git_no_verify_still_disables_checks():
    assert _disables("git commit --no-verify")


def test_shared_argv_parser_closes_safe_adjacency_gaps():
    assert _fires("rm -r -f ./build")
    assert _fires("git -C repo reset --hard")
    assert _fires("mkfs -t ext4 /dev/sdb1")
    assert not _fires("git clean -d")
    assert not _fires("git checkout -- ./file")


def test_documented_intentional_long_rm_gap_stays_out_of_scope():
    assert not _fires("rm --recursive --force ./build")


# ---- scratch-space cleanup: every target under a temp root destroys no work ---------------------
def test_rm_rf_of_scratchpad_dir_is_not_destruction():
    # discriminant: every rm target lies under /tmp/ or a /scratchpad/ component
    assert not _fires("rm -rf /tmp/claude-0/x/scratchpad/mesh")
    assert not _fires("rm -rf /var/tmp/build-cache /tmp/a")
    assert not _fires('rm -rf "$TMPDIR/run1" ${TMPDIR}/run2')
    assert not _fires("rm -rf /home/user/proj/scratchpad/out")


def test_rm_rf_mixing_a_temp_target_with_a_work_target_is_destruction():
    # discriminant: one target (src) is outside every temp root
    assert _fires("rm -rf /tmp/x src")
    assert _fires("rm -rf src")
    assert _fires("rm -rf build/")


def test_temp_root_itself_or_an_escape_from_it_is_destruction():
    # discriminant: target is the bare root, or '..' normalizes it out of the temp root
    assert _fires("rm -rf /tmp")
    assert _fires("rm -rf /tmp/")
    assert _fires("rm -rf $TMPDIR")
    assert _fires("rm -rf /tmp/../home/user/src")
    assert _fires("rm -rf /x/scratchpad/../../src")
    assert _fires("rm -rf /tmpfoo/x")


def test_git_worktree_remove_and_prune_are_not_destruction():
    # discriminant: git subcommand is `worktree`, whose checkout is disposable
    assert not _fires("git worktree remove /tmp/wt3")
    assert not _fires("git worktree remove --force ../wt3")
    assert not _fires("git worktree prune")
    assert _fires("git clean -fdx")
    assert _fires("git reset --hard")


# ---- 3.4.7 record, 2026-09-28: 14 false destruct fires were `rm -rf` of a scratch variable ----
import pytest as _pytest


@_pytest.mark.parametrize("cmd, destructive", [
    ("d=$(mktemp -d); cp -r . $d; rm -rf $d", False),
    ("S=/tmp/claude-0/x/scratchpad; rm -rf $S/sc", False),
    ("S=/tmp/x; P=$S/plant; rm -rf $P", False),
    ("rm -rf $d", True),                         # unbound here: not known to be scratch
    ("X=src; rm -rf $X", True),
    ("S=/tmp/x; rm -rf $S/../../home", True),    # escapes the temp root
    ("rm -rf src", True),
])
def test_a_scratch_variable_bound_in_the_same_command_is_scratch(cmd, destructive):
    from makoto.substrate._canonAtoms import is_destructive_command
    assert is_destructive_command(cmd) == destructive


@_pytest.mark.parametrize("cmd, err, interrupted, error_state", [
    ("for m in a b; do codex exec -m $m OK > o-$m; grep -c bubblewrap o-$m; done", "Exit code 1\n0", False, False),
    ("grep x nofile", "Exit code 2\ngrep: nofile: No such file", False, True),
    ("python3 -m pytest -q", "Exit code 1\n1 failed", False, True),
    ("grep -c x f; false", "Exit code 1", False, True),
    ("grep -r x .", "", True, True),
])
def test_a_search_that_found_nothing_is_not_an_error_state(cmd, err, interrupted, error_state):
    """canon.timeout's one false fire on the 3.4.7 record: grep's exit 1 means no line matched."""
    from makoto.checks.switch import timed_out
    assert timed_out({"name": "Bash", "input": {"command": cmd},
                      "result": {"error": err, "interrupted": interrupted}}) == error_state


# ---- a Codex gpt-6-astra read of 149d148..cf7c2c1: bindings follow the shell, not the text ----
@_pytest.mark.parametrize("cmd", [
    "D=src; rm -rf $D; D=/tmp/safe",              # bound after the removal
    "D=src; (D=/tmp/safe); rm -rf $D",            # bound in a subshell
    "D=src; D=/tmp/safe true; rm -rf $D",         # an env prefix binds nothing here
    "D=src; # D=/tmp/safe\nrm -rf $D",            # a comment
    'D=src; echo "example D=/tmp/safe"; rm -rf $D',  # a quoted string
    "D=src/mktemp-cache; rm -rf $D",              # the word, not the command substitution
])
def test_a_binding_counts_only_where_the_shell_makes_it(cmd):
    from makoto.substrate._canonAtoms import is_destructive_command
    assert is_destructive_command(cmd)


@_pytest.mark.parametrize("cmd", ["false && grep x /dev/null", "false | grep x /dev/null"])
def test_a_search_reached_through_a_failure_does_not_hide_it(cmd):
    from makoto.checks.switch import timed_out
    assert timed_out({"name": "Bash", "input": {"command": cmd}, "result": {"error": "Exit code 1"}})


@_pytest.mark.parametrize("cmd", [
    "D=src; (D=/tmp/safe); (rm -rf $D)",           # a second subshell starts from the parent's D
    "D=$(pwd); rm -rf $D",                         # a substitution that is not mktemp
])
def test_a_scope_or_substitution_that_is_not_scratch_stays_destructive(cmd):
    from makoto.substrate._canonAtoms import is_destructive_command
    assert is_destructive_command(cmd)


def test_the_statement_scanner_parses_a_command_once(monkeypatch):
    import shlex
    from makoto.core import _shell
    _shell.statements.cache_clear()
    calls, real = [], shlex.shlex
    monkeypatch.setattr(shlex, "shlex", lambda *a, **k: calls.append(1) or real(*a, **k))
    for _ in range(5):
        _shell.statements("d=$(mktemp -d); rm -rf $d")
    assert len(calls) == 1
