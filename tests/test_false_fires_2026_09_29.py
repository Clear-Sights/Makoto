"""The three live false fires of 2026-09-29 and the two mesh misses, each with its guard so the fix
cannot blind the row. The end-to-end cases are in tools/mesh (H/ and C/ref_reword1, D/running_reword1)."""
from makoto.kit import reads_only, repeats_launch
from makoto.substrate._canonAtoms import is_destructive_command
from makoto.checks.lineage import _move_targets
from makoto.checks.switch import _OWN_START_RX


def _launch(prompt, description="", **extra):
    return {"tool_name": "Agent", "tool_input": dict(prompt=prompt, description=description, **extra)}


def test_a_worker_sent_only_to_read_is_a_probe():
    assert reads_only(_launch("Read PLANS/MAKOTO2.md and report its NEXT section. Do not edit anything."))
    assert reads_only(_launch("anything", subagent_type="Explore"))


def test_a_worker_that_reads_then_changes_is_not():
    assert not reads_only(_launch("Read src/parser.py and fix the off-by-one."))
    assert not reads_only(_launch("Refactor the auth module"))


def test_a_different_brief_is_another_job():
    assert not repeats_launch(_launch("Read the mesh table"), _launch("Write the memory file"))


def test_the_same_brief_again_is_a_relaunch():
    assert repeats_launch(_launch("", "run worker"), _launch("", "run worker again"))


def test_a_loop_body_binding_reads_as_scratch():
    assert not is_destructive_command("for i in 1 2; do d=/tmp/claude-0/c$i; rm -rf $d; done")
    assert is_destructive_command("for i in 1 2; do d=src; rm -rf $d; done")


def test_a_ref_read_out_of_a_file_owes_the_file():
    assert _move_targets(["git", "checkout", "$(cat branch_to_use.txt"], set(), "/nonexistent") == [
        "branch_to_use.txt"]
    assert _move_targets(["git", "checkout", "$ref"], set(), "/nonexistent") == []


def test_the_speakers_own_start_binds_a_running_claim():
    assert _OWN_START_RX.search("I restarted the payment service; it's fully operational now.")
    assert not _OWN_START_RX.search("I started reviewing the docs; the site is live.")
