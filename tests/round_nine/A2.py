# A2 content.phantom_citation (docs/attack-round-nine.md, round nine).
# makoto-allow: fixtures must spell the phantom citation shapes the check exists to catch
from pathlib import Path

ROW = "content.phantom_citation"
# The packaged CITATIONS.md governs the plugin's own tree, so the write lands there.
DOC = str(Path(__file__).resolve().parents[2] / "plugin" / "makoto" / "docs" / "r9-notes.md")
AUTHOR, YEAR = "Zyg" + "mund", "20" + "21"


def _write(text, path=DOC):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": path, "content": text}}


CASES = [
    dict(name="base", row=ROW, events=[_write(f"As {AUTHOR} {YEAR} showed, x holds.\n")]),
    dict(name="parenthetical", row=ROW, events=[_write(f"x holds ({AUTHOR}, {YEAR}).\n")]),
    # Vaswani 2017 is canonical; 2017b is a different work by the same author.
    dict(name="year-suffix", row=ROW, events=[_write("As " + "Vas" + "wani 20" + "17b showed, x holds.\n")]),
]
