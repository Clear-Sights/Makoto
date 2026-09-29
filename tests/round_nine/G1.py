# G1 content.phantom_citation (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the phantom citation shapes the check exists to catch
from pathlib import Path

ROW = "content.phantom_citation"
_DOCS = Path(__file__).resolve().parents[2] / "plugin" / "makoto" / "docs"
AUTHOR, YEAR = "Quil" + "leran", "20" + "19"


def _write(text, name):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": str(_DOCS / name), "content": text}}


CASES = [
    dict(name="base", row=ROW, events=[_write(f"Per {AUTHOR} {YEAR}, x holds.\n", "r9-g1.md")]),
    dict(name="rst", row=ROW, events=[_write(f"Notes\n=====\n\n{AUTHOR} {YEAR} showed x.\n", "r9-g1.rst")]),
    dict(name="parenthetical", row=ROW, events=[_write(f"x holds ({AUTHOR}, {YEAR}).\n", "r9-g1.md")]),
]
