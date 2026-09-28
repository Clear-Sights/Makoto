"""START's open steps each carry a projection, and every void it leaves is a row for an open step."""
from __future__ import annotations

import csv
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECTION = re.compile(r"^\s+projection[ :(]", re.M)


def open_steps(text: str) -> dict[str, str]:
    """Numbered steps not struck through, each with its whole body."""
    body = text.split("\nThe steps:\n", 1)[1]
    parts = re.split(r"^(\d+)\. ", body, flags=re.M)[1:]
    return {n: b for n, b in zip(parts[::2], parts[1::2]) if not b.startswith("~~")}


def test_every_open_step_carries_a_projection_line():
    steps = open_steps((REPO / "START.md").read_text(encoding="utf-8"))
    assert steps, "no open steps read"
    missing = [n for n, b in steps.items() if not PROJECTION.search(b)]
    assert not missing, f"open steps with no projection: {missing}"


def test_the_projection_check_reads_red_on_its_plant():
    planted = "The steps:\n6. Re-grade worth.\n   check: x. owner: next.\n"
    steps = open_steps("x\n" + planted)
    assert not PROJECTION.search(steps["6"])


def test_every_void_names_an_open_step_and_a_measure():
    steps = open_steps((REPO / "START.md").read_text(encoding="utf-8"))
    rows = list(csv.DictReader((REPO / "docs/v9/VOIDS.tsv").open(encoding="utf-8"), delimiter="\t"))
    assert rows
    for r in rows:
        assert r["step"] in steps, r
        assert r["void"] and r["measured_by"], r


STOP = "Stop: at the cap, record the measured number in VOIDS and go on."


def test_every_open_step_carries_the_stop_line():
    steps = open_steps((REPO / "START.md").read_text(encoding="utf-8"))
    assert not [n for n, b in steps.items() if STOP not in b]


def numeric_caps(rows: list[dict]) -> list[dict]:
    """Rows whose caps are not whole numbers: a step cannot end at a cap that is not a number."""
    return [r for r in rows if not all((r.get(k) or "").isdigit() for k in ("cap_model_calls", "cap_minutes"))]


def test_every_void_has_a_numeric_cap_and_the_check_reads_red_on_its_plant():
    rows = list(csv.DictReader((REPO / "docs/v9/VOIDS.tsv").open(encoding="utf-8"), delimiter="\t"))
    assert not numeric_caps(rows)
    assert numeric_caps([dict(rows[0], cap_minutes="one replay")])


def test_the_step_12_projection_runs_with_no_model_and_names_every_entry():
    import subprocess
    import sys
    out = subprocess.run([sys.executable, str(REPO / "tools/project.py"), "12"], capture_output=True,
                         text=True)
    assert out.returncode == 0, out.stderr
    sys.path.insert(0, str(REPO / "tools"))
    import register_map
    count = sum(1 for ln in register_map.REGISTER.read_text(encoding="utf-8").splitlines()
                if register_map.ENTRY_RX.match(ln))
    assert out.stdout.startswith(f"PROJECT 12 entries={count} "), out.stdout


def test_every_open_step_names_its_check_inputs_and_owner():
    """A step with no `inputs:` leaves the next session guessing what to open first."""
    steps = open_steps((REPO / "START.md").read_text(encoding="utf-8"))
    missing = [(n, f) for n, b in steps.items() for f in ("check:", "inputs:", "owner:") if f not in b]
    assert not missing, missing


INPUTS = re.compile(r"\binputs?:\s*(.*?)(?=\s(?:owner|check|plant|cap|projection|Stop|after|cost):|\Z)", re.S)
ITEMS = re.compile(r",\s*(?:and\s+)?|;\s*|\s+and\s+(?=(?:the|a|an)\b)")
DESCRIBED = re.compile(r"(?<!in )\b(?:the|a|an)\s+(?:[\w'-]+\s+){0,3}(?:case list|list|table)\b", re.I)
PATHLIKE = re.compile(r"`[^`]+`|[\w.-]+/[\w./-]+|\b[\w-]+\.(?:md|tsv|py|sh|txt|json|jsonl)\b")
CLONE = re.compile(r"clone of `[\w.-]+/([\w.-]+)`")
LAUNCH_CLONES = ("Scour", "Measure-Zero")   # the launch checklist clones these beside the repository


def unclosed_inputs(text: str, root: Path = REPO) -> list[tuple[str, str]]:
    """Inputs of open steps that a launched session cannot open: a document named by description
    ("the attack's case list"), or a path this repository does not carry. Paths under `~` are the
    running session's; paths in a clause naming a launch clone are that clone's."""
    bad = []
    for n, body in open_steps(text).items():
        for clause in (" ".join(c.split()) for c in INPUTS.findall(body)):
            bad += [(n, i) for i in ITEMS.split(clause) if DESCRIBED.search(i) and not PATHLIKE.search(i)]
            clone = CLONE.search(clause)
            if clone:
                bad += [] if clone.group(1) in LAUNCH_CLONES else [(n, clone.group(0))]
                continue
            words = (w.rstrip(".,:;") for span in re.findall(r"`([^`]+)`", clause) for w in span.split())
            bad += [(n, w) for w in words if ("/" in w or re.search(r"\.[A-Za-z0-9]{1,6}$", w))
                    and not w.startswith(("~", "/", "$", "-", "http")) and "<" not in w and not (root / w).exists()]
    return bad


def test_every_open_input_is_a_path_the_session_can_open():
    """Closure (Launch rows, 2026-09-28): the attack's case list was named, not cited, and lived only
    in the project folder a launched session cannot see."""
    text = (REPO / "START.md").read_text(encoding="utf-8")
    assert len(INPUTS.findall(text)) >= 5
    assert unclosed_inputs(text) == []


def test_the_closure_check_reads_red_on_its_plants():
    text = (REPO / "START.md").read_text(encoding="utf-8")
    cited = "the round-nine cases in\n    `docs/attack-round-nine.md`."
    assert cited in text
    assert unclosed_inputs(text.replace(cited, "the attack's case list, copied in later."))
    assert unclosed_inputs(text.replace(cited, "the cases in `docs/attack-round-ten.md`."))
    assert unclosed_inputs(text.replace("clone of `Clear-Sights/Scour`", "clone of `Clear-Sights/Elsewhere`"))
