"""One count per register (START step 12): the entry count is read off docs/REGISTER.md by script,
and any document that types a count of the whole register must agree with it.

The kind of claim is a number carried by the register's own unit, `N entries`, `N blindspots`,
`N register ids` or a tool line's `entries=N`. A narrowed count ("the last 14 register entries")
counts a subset and is not the register's count. Plant: a wrong count typed into README.md reads red.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEXT = (".md", ".txt", ".toml", ".json", ".yaml", ".yml", ".rst")
_TYPED = re.compile(r"(?<![\w.-])(\d[\d,]*)\s+(?:register\s+)?(?:entries|blindspots|ids)\b(?!=)|\bentries=(\d+)\b",
                    re.IGNORECASE)
_NARROWED = re.compile(r"\b(?:last|first|remaining|other|new|these|those|open|refused|parsed)\s+$",
                       re.IGNORECASE)


def register_count() -> int:
    sys.path.insert(0, str(ROOT / "tools"))
    import register_map
    return sum(1 for ln in register_map.REGISTER.read_text(encoding="utf-8").splitlines()
               if register_map.ENTRY_RX.match(ln))


def typed_counts(text: str):
    for m in _TYPED.finditer(text):
        if _NARROWED.search(text[max(0, m.start() - 30):m.start()]):
            continue
        yield int((m.group(1) or m.group(2)).replace(",", "")), m.group(0)


def disagreements(files, count):
    return [f"{p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}: `{shown}` but the register has {count}"
            for p in files for n, shown in typed_counts(p.read_text(encoding="utf-8", errors="ignore"))
            if n != count]


def _docs():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout
    return [ROOT / f for f in out.splitlines() if f.endswith(TEXT) and (ROOT / f).is_file()]


def test_every_typed_register_count_agrees_with_the_register_file():
    assert register_count() > 0
    assert disagreements(_docs(), register_count()) == []


def test_plant_a_wrong_count_in_readme_reads_red(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text((ROOT / "README.md").read_text(encoding="utf-8")
                      + f"\nMakoto covers all {register_count() + 3} blindspots.\n", encoding="utf-8")
    bad = disagreements([readme], register_count())
    assert len(bad) == 1 and "blindspots" in bad[0]


def test_a_narrowed_count_is_not_the_register_count():
    assert list(typed_counts("the foundation for the last 14 register entries")) == []
    assert [n for n, _ in typed_counts("PROJECT 12 entries=5 both=2")] == [5]
