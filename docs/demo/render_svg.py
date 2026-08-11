"""docs/demo/render_svg.py — render each logged demo scenario into a terminal-style SVG.

Reads `docs/demo/logs/<scenario>.json` (written by render_demo.py from REAL dispatcher runs) and
renders `docs/demo/screenshots/<scenario>.svg`. Every visible line is the scenario's genuine
logged stdout/stderr (plus the step titles and display commands from the log itself) — nothing is
hand-written into the image. Two DISPLAY-ONLY transforms, both decoding rather than authoring:

  1. A stdout line that parses as a hook-decision JSON object (`hookSpecificOutput`) is unfolded
     into the decision tag plus the reason/context text the agent actually sees — the text is the
     log's own string value, verbatim, just JSON-unescaped and split on its real newlines.
  2. `render_demo.py` records stable placeholders for its temporary workspace and checkout before
     these logs are committed, so no renderer-side path redaction is needed.

Standard library only, like the rest of the package. The one formatting nicety this script wants
is the footer's human-readable byte count ("captured 1.4 kB output"), and `_naturalsize` below
does it in six lines. It used to come from `humanize`: a whole third-party package, installed
by everyone who touched the repo, for a single call in a single demo caption. That trade was
never worth making — the core refuses unearned weight, and a demo script is not an exemption.
"""
from __future__ import annotations

import json
from pathlib import Path


DEMO_DIR = Path(__file__).parent
LOGS_DIR = DEMO_DIR / "logs"
SHOTS_DIR = DEMO_DIR / "screenshots"

W = 700
PAD = 14
LINE_H = 15
FONT = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
COLORS = {
    "bg": "#0d1117", "chrome": "#161b22", "text": "#c9d1d9", "dim": "#8b949e",
    "green": "#3fb950", "red": "#f85149", "yellow": "#d29922", "cyan": "#79c0ff",
    "title": "#c9d1d9",
}
FONT_SIZE = 11.5
# Monospace advance width: ui-monospace/Menlo/Consolas all sit at ~0.60 em per character, so the
# per-char pixel width is 0.6023 * FONT_SIZE and the line capacity is exactly the content width
# (frame minus both pads) over that -- derived, not eyeballed, so no line can overrun the frame.
CHAR_W = 0.6023 * FONT_SIZE
CAP = int((W - 2 * PAD) / CHAR_W)
_HANG = "  "                       # continuation indent, deducted from the capacity


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _naturalsize(count: int) -> str:
    """Decimal byte units — 1000, not 1024 — matching `humanize.naturalsize` defaults on every
    non-negative input: "0 Bytes", "1 Byte", "999 Bytes", "1.0 kB", "1.2 MB", "1.0 TB".

    The carry test is on the ROUNDED value, not the raw one. 999_999_999_999 divides down to
    999.999999999 GB, which is under 1000 and so looks like it belongs in GB — but it prints as
    "1000.0 GB", a unit boundary crossed by the formatting rather than by the arithmetic. Testing
    `round(size, 1)` promotes it to "1.0 TB", which is what humanize says.
    """
    if count == 1:
        return "1 Byte"
    if count < 1000:
        return f"{count} Bytes"
    size = float(count)
    for unit in ("kB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB", "RB", "QB"):
        size /= 1000
        if round(size, 1) < 1000 or unit == "QB":
            return f"{size:.1f} {unit}"


def _wrap(line: str) -> list:
    """Word-boundary wrap into <= CAP-char pieces (continuations hang-indented): break at the
    last space that fits; only an unbroken run longer than a whole line is ever split mid-word."""
    out, indent = [], ""
    while len(indent) + len(line) > CAP:
        room = CAP - len(indent)
        cut = line.rfind(" ", 0, room + 1)
        if cut <= 0:
            cut = room
        out.append(indent + line[:cut].rstrip())
        line = line[cut:].lstrip()
        indent = _HANG
    out.append(indent + line)
    return out


def _color_for(line: str) -> str:
    s = line.strip()
    if s.startswith("[makoto ERROR]") or "ERROR" in s.split(" ")[:2]:
        return COLORS["red"]
    if "ADVISORY" in s[:60]:
        return COLORS["yellow"]
    if s.startswith("retry:"):
        return COLORS["yellow"]
    if s.startswith(("{", "}", '"')) or s.startswith(("  \"", " \"")):
        return COLORS["cyan"]
    return COLORS["text"]


def _unfold_decision(stdout: str) -> list | None:
    """docstring point 1: a hook-decision JSON stdout -> the lines the agent actually sees.
    Returns [(text, color)] or None if this stdout is not a single hook-decision object."""
    s = stdout.strip()
    if not s.startswith("{"):
        return None
    try:
        obj = json.loads(s)
    except Exception:
        return None
    hso = obj.get("hookSpecificOutput") if isinstance(obj, dict) else None
    if not isinstance(hso, dict):
        return None
    out = []
    if "permissionDecision" in hso:
        out.append((f"-> permissionDecision: {hso['permissionDecision']}", COLORS["red"]))
        for ln in (hso.get("permissionDecisionReason") or "").splitlines():
            out.append((ln, COLORS["red"] if ln.startswith("makoto:") else COLORS["text"]))
    if "additionalContext" in hso:
        for ln in (hso.get("additionalContext") or "").splitlines():
            out.append((ln, COLORS["yellow"]))
    return out or None


def _render(scenario: str) -> None:
    log = json.loads((LOGS_DIR / f"{scenario}.json").read_text())
    rows = []  # (text, color, italic)
    total_bytes = 0
    for step in log["steps"]:
        rows.append((f"# {step['title']}", COLORS["dim"], True))
        rows.append((f"$ {step['display_cmd']}", COLORS["green"], False))
        total_bytes += len(step["stdout"].encode()) + len(step["stderr"].encode())
        unfolded = _unfold_decision(step["stdout"])
        if unfolded is not None:
            for raw, color in unfolded:
                for piece in _wrap(raw):
                    rows.append((piece, color, False))
        else:
            for raw in step["stdout"].splitlines():
                if raw.strip() == "":
                    continue
                for piece in _wrap(raw):
                    rows.append((piece, _color_for(raw), False))
        for raw in step["stderr"].splitlines():
            if raw.strip() == "":
                continue
            for piece in _wrap(raw):
                rows.append((piece, _color_for(raw), False))
        rows.append((f"(exit {step['exit']})", COLORS["dim"], False))
        rows.append(("", COLORS["text"], False))
    rows.append((f"captured {_naturalsize(total_bytes)} of genuine dispatcher output",
                 COLORS["dim"], True))

    height = PAD * 2 + 34 + LINE_H * len(rows)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
        f'viewBox="0 0 {W} {height}" font-family="{FONT}" font-size="{FONT_SIZE}">',
        f'<rect width="{W}" height="{height}" rx="8" fill="{COLORS["bg"]}"/>',
        f'<rect width="{W}" height="30" rx="8" fill="{COLORS["chrome"]}"/>',
        f'<rect y="22" width="{W}" height="8" fill="{COLORS["chrome"]}"/>',
        '<circle cx="18" cy="15" r="5" fill="#ff5f56"/>',
        '<circle cx="36" cy="15" r="5" fill="#ffbd2e"/>',
        '<circle cx="54" cy="15" r="5" fill="#27c93f"/>',
        f'<text x="{W / 2:.0f}" y="19" text-anchor="middle" fill="{COLORS["dim"]}">'
        f'makoto demo — {scenario}</text>',
    ]
    y = 34 + PAD
    for text, color, italic in rows:
        if text:
            style = ' font-style="italic"' if italic else ""
            parts.append(f'<text x="{PAD}" y="{y}" fill="{color}"{style} xml:space="preserve">'
                         f'{_esc(text)}</text>')
        y += LINE_H
    parts.append("</svg>")
    SHOTS_DIR.mkdir(exist_ok=True)
    out = SHOTS_DIR / f"{scenario}.svg"
    out.write_text("\n".join(parts))
    print(f"wrote {out} ({len(rows)} lines)")


def main() -> None:
    for scenario in ("block", "receipt", "configchange"):
        _render(scenario)


if __name__ == "__main__":
    main()
