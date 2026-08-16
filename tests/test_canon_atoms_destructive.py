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
