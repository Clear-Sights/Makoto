"""gate.pasted_fix (register H3 FIX DRAWN FROM FIXES) -- the order, and the three narrowings.

The check asks one question -- did the same repair reach a second site with nothing run in
between -- so the tests are the fault itself, then the ORDER that discharges it, then one group
per narrowing the rate measurement bought (the module docstring carries those rates). Each
narrowing has a test that goes red when it is removed, which is what `tests/mutate`-style plants
on a copy of this tree were used to confirm before this file landed.

The malformed-row tolerance is NOT restated here: it is one whole-set law over every
history-eating gate in tests/test_stop_gate_level_invariant.py, where a gate added without it
reddens.
"""
from __future__ import annotations

from makoto.checks.lineage import pasted_CHECK as CHECK, _blocks, _kept_lines, pasted_fix_gate

# Four substantial lines: a null-default and a range guard. The grain is four, so this is the
# shortest repair the gate can see -- see the module docstring's named recall bound.
REPAIR = ("if timeout is None:\n"
          "    timeout = DEFAULT_TIMEOUT\n"
          "if timeout < 0:\n"
          "    raise ValueError(timeout)\n")


def _landing(path, new_string=REPAIR, tool_name="Edit"):
    key = {"Write": "content"}.get(tool_name, "new_string")
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": tool_name,
                        "tool_input": {"file_path": path, "old_string": "pass",
                                       key: new_string},
                        "tool_response": {}}}


def _run(command):
    return {"payload": {"hook_event_name": "PostToolUse", "tool_name": "Bash",
                        "tool_input": {"command": command},
                        "tool_response": {"stdout": "58 passed in 2.0s"}}}


# ---- the fault ------------------------------------------------------------------------------

def test_fires_when_the_same_repair_reaches_a_second_file():
    """The scenario tests/test_stop_gate_level_invariant.py names for this gate."""
    finding = pasted_fix_gate([_landing("src/reader.py"), _landing("src/writer.py")])
    assert finding is not None
    assert finding.pattern_id == "gate.pasted_fix"
    assert finding.level == "advisory"
    assert finding.file == "src/writer.py", "the finding belongs at the UNCHECKED second site"
    assert "src/reader.py" in finding.message, "the finding must name the site it was drawn from"


def test_one_landing_alone_is_not_a_finding():
    assert pasted_fix_gate([_landing("src/reader.py")]) is None


def test_an_empty_history_is_not_a_finding():
    assert pasted_fix_gate([]) is None
    assert pasted_fix_gate(None) is None


# ---- the order, which IS the check ------------------------------------------------------------

def test_a_verifier_run_between_the_landings_discharges_it():
    """*One change per pass.* A run between the two landings is the pass, so the second site's
    correctness was checked rather than inferred."""
    assert pasted_fix_gate([_landing("src/reader.py"),
                            _run("python3 -m pytest -q"),
                            _landing("src/writer.py")]) is None


def test_a_run_before_the_first_landing_does_not_discharge_it():
    """The distinction from `kit.unmet_obligation_gate`, whose guard pays for the rest of the
    session once seen: here a run that precedes BOTH landings separates neither of them."""
    assert pasted_fix_gate([_run("python3 -m pytest -q"),
                            _landing("src/reader.py"),
                            _landing("src/writer.py")]) is not None


def test_a_run_after_both_landings_does_not_discharge_it():
    assert pasted_fix_gate([_landing("src/reader.py"),
                            _landing("src/writer.py"),
                            _run("python3 -m pytest -q")]) is not None


def test_a_command_that_is_not_a_verifier_does_not_discharge_it():
    """The vocabulary is `kit.ran_a_verifier` and nothing wider: `ls` is not a pass."""
    assert pasted_fix_gate([_landing("src/reader.py"),
                            _run("ls -la src/"),
                            _landing("src/writer.py")]) is not None


# ---- narrowing 1: the same text, in two DISTINCT files ----------------------------------------

def test_two_landings_in_the_same_file_are_not_a_finding():
    """Editing one file twice is one site, however many times it is touched. Without this the
    gate fires on any iteration on a single file."""
    assert pasted_fix_gate([_landing("src/reader.py"), _landing("src/reader.py")]) is None


def test_two_different_changes_in_two_files_are_not_a_finding():
    """The naive reading -- two edits with no run between them -- fires on 73.5% of this tree's
    own commits. This is the test that fails when the gate is widened back to it."""
    other = ("if retries is None:\n"
             "    retries = DEFAULT_RETRIES\n"
             "if retries > MAX:\n"
             "    raise ValueError(retries)\n")
    assert pasted_fix_gate([_landing("src/reader.py"),
                            _landing("src/writer.py", other)]) is None


def test_a_repair_shorter_than_the_grain_is_not_a_finding():
    """The named recall bound, in a test: three substantial lines is under the grain, and a
    one-line repeat is indistinguishable from convention on this tree's record (21.1% against
    3.2%)."""
    short = "if timeout is None:\n    timeout = DEFAULT_TIMEOUT\nlog.debug(timeout)\n"
    assert pasted_fix_gate([_landing("src/reader.py", short),
                            _landing("src/writer.py", short)]) is None


# ---- narrowing 2: a change to what EXISTS -----------------------------------------------------

def test_two_written_files_are_not_a_finding():
    """A file being WRITTEN carries the house import header, and admitting written files takes
    the rate from 3.8% to 9.2% on this tree's own history -- every added fire the header or a
    build artifact. A fix is edited into something already there."""
    assert pasted_fix_gate([_landing("src/reader.py", tool_name="Write"),
                            _landing("src/writer.py", tool_name="Write")]) is None


def test_a_write_then_an_edit_of_the_same_block_still_fires():
    """Narrowing 2 excludes a Write from TRIGGERING a fire (see the test above), not from being
    REMEMBERED as a possible first site. A block Written into a brand-new file and then Edited
    into a second, existing one is the same repair-transfer as two Edits -- the second site's
    correctness is still drawn from the first rather than checked."""
    finding = pasted_fix_gate([_landing("src/new_module.py", tool_name="Write"),
                               _landing("src/writer.py")])
    assert finding is not None
    assert finding.pattern_id == "gate.pasted_fix"
    assert finding.file == "src/writer.py"


def test_a_multiedit_is_a_change_to_what_exists():
    """MultiEdit is an Edit that carries several replacements; `kit.introduced_text` joins
    them, so the second landing is seen exactly as a plain Edit's would be."""
    multi = {"payload": {"hook_event_name": "PostToolUse", "tool_name": "MultiEdit",
                         "tool_input": {"file_path": "src/writer.py",
                                        "edits": [{"old_string": "pass", "new_string": REPAIR}]},
                         "tool_response": {}}}
    assert pasted_fix_gate([_landing("src/reader.py"), multi]) is not None


# ---- narrowing 3: substance -------------------------------------------------------------------

def test_a_block_of_nothing_but_convention_is_not_a_finding():
    """A window of imports, comments and decorators is convention travelling, and convention
    travels legitimately. This is the house import header the measurement named."""
    header = ("from __future__ import annotations\n"
              "import ast\n"
              "# Knight-Leveson: stdlib ast/re only.\n"
              "from typing import Optional\n")
    assert pasted_fix_gate([_landing("src/reader.py", header),
                            _landing("src/writer.py", header)]) is None


def test_one_substantial_line_in_the_window_is_enough():
    """The filter drops a window with NO content of its own, not every window that mentions an
    import -- a repair that begins with its import is still a repair."""
    mixed = ("from math import ceil\n"
             "import os\n"
             "size = ceil(total / pages)\n"
             "return size\n")
    assert pasted_fix_gate([_landing("src/reader.py", mixed),
                            _landing("src/writer.py", mixed)]) is not None


# ---- the normalization ------------------------------------------------------------------------

def test_a_reindented_paste_is_the_same_paste():
    """The margin goes and internal whitespace collapses, so moving a fix into a deeper block
    does not make it new text. Without the normalization the gate goes quiet on exactly the
    paste that had to be adjusted to fit its second site."""
    deeper = "".join("        " + line + "\n" for line in REPAIR.splitlines())
    assert pasted_fix_gate([_landing("src/reader.py"),
                            _landing("src/writer.py", deeper)]) is not None


def test_blank_and_bracket_only_lines_do_not_pad_a_block():
    """`_kept_lines` drops what carries nothing, so four substantial lines spread over eight
    source lines are still one block -- and four closers are not."""
    assert _kept_lines("a = 1\n\n   )\nb = 2\n") == ["a = 1", "b = 2"]
    assert _blocks(_kept_lines(")\n}\n]\n,\n")) == []


# ---- the registration -------------------------------------------------------------------------

def test_the_check_ships_at_the_stop_edge_reading_history_only():
    assert CHECK.id == "gate.pasted_fix"
    assert CHECK.applies_at == "Stop"
    assert CHECK.eats == frozenset({"history"})
