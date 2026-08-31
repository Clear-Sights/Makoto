"""Text-mode I/O on the hook path names its encoding, and the check that says so has teeth.

THE INCIDENT. A live dispatch reported:

    makoto: 1 check-evaluation fault(s) on this call -- [exception] UnicodeDecodeError:
    'charmap' codec can't decode byte 0x9d in position 3017: character maps to <undefined>.
    The call was ALLOWED WITHOUT BEING CHECKED (fail-open).

The fail-open is correct and deliberate (`dispatch.py:197-211`): a broken gate must not wedge the
session, and the `systemMessage` is what makes it loud. The DEFECT is the crash that provoked it.
`charmap` is the Windows platform default, so a text read had named no encoding. Byte 0x9d is
undefined in cp1252 and is the third byte of U+201D -- a right double quotation mark. Any file
carrying one curly quote kills a check that reads it under the platform default, on one OS and
not the other, which is why it survived every run in this estate.

WHY A LAW AND NOT SIX EDITS. The crash named one site. A grep for the shape returned ~879 lines
across the estate, which is a fact about grep: it counts test files and misses calls whose
`encoding=` sits on a continuation line -- `dispatch.py:266` was on the grep's list and has
carried an explicit encoding all along. Parsed rather than grepped, `plugin/` held SEVEN real
sites. Fixing only the one that fired would leave six twins waiting for a different curly quote.

THE SAME SEVEN SITES EXIST IN `makoto-dev`, and this is the shipped copy -- the one whose fault
was actually reported. Landing the fix in the development tree alone would leave the plugin
users install exactly as it was.

SCOPE, STATED. This law covers `plugin/` -- the code that runs inside the host's hook, where a
crash costs a check that nobody was told did not run. This tree carries 9 further sites outside
`plugin/`; those are developer entrypoints where a decode crash is immediate
and loud, and they are recorded here rather than silently excluded. Widening this law to them is
a separate change with a separate argument, not an oversight.
"""

from __future__ import annotations

import ast
import pathlib
import unittest

PLUGIN = pathlib.Path(__file__).resolve().parent.parent / "plugin"
READERS = {"read_text", "write_text"}
RUNNERS = {"run", "check_output", "Popen", "call", "check_call"}


def unstated_sites(root: pathlib.Path) -> list[str]:
    """Every text-mode call under `root` that does not name an encoding.

    Parsed, never grepped: a keyword counts wherever in the call it appears, and a binary-mode
    `open` is not a text read. Both distinctions were mistakes a grep made on this exact code.
    """
    found = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            keywords = {k.arg for k in node.keywords if k.arg}
            if "encoding" in keywords:
                continue
            name = (node.func.attr if isinstance(node.func, ast.Attribute)
                    else node.func.id if isinstance(node.func, ast.Name) else None)
            hit = None
            if name in READERS:
                hit = name
            elif name == "open":
                mode = ""
                if node.args[1:2] and isinstance(node.args[1], ast.Constant):
                    mode = str(node.args[1].value)
                for keyword in node.keywords:
                    if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                        mode = str(keyword.value.value)
                hit = None if "b" in mode else "open"
            elif name in RUNNERS and ({"text", "universal_newlines"} & keywords):
                hit = f"subprocess.{name}"
            if hit:
                found.append(f"{path.relative_to(root)}:{node.lineno} {hit}")
    return found


class EncodingIsStatedOnTheHookPath(unittest.TestCase):
    def test_no_plugin_text_io_relies_on_the_platform_default(self):
        unstated = unstated_sites(PLUGIN)
        self.assertEqual(unstated, [], "text-mode I/O with no encoding= under plugin/: "
                                       + "; ".join(unstated))

    def test_the_check_can_fail(self):
        """NON-VACUITY. A law that scans a tree can pass because it found nothing to scan."""
        import tempfile
        with tempfile.TemporaryDirectory() as name:
            root = pathlib.Path(name)
            (root / "clean.py").write_text(
                'p.read_text(encoding="utf-8")\nopen(f, "rb")\n', encoding="utf-8")
            self.assertEqual(unstated_sites(root), [], "a stated encoding must not be flagged")
            (root / "dirty.py").write_text("p.read_text()\n", encoding="utf-8")
            self.assertEqual(len(unstated_sites(root)), 1,
                             "a bare read_text() must be flagged")

    def test_the_incident_byte_is_read_by_utf8_and_not_by_the_platform_default(self):
        """The actual fault, reproduced: one curly quote, two codecs, two outcomes.

        This is what makes the fix a fix rather than a preference. Pinning utf-8 does not merely
        change which error appears -- these bytes are VALID utf-8 and undefined in cp1252, so the
        pin is the difference between the check running and the call going unchecked.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as name:
            path = pathlib.Path(name) / "module.py"
            path.write_text('NOTE = "he said ”hello”"\n', encoding="utf-8")
            self.assertIn(0x9D, path.read_bytes(), "the fixture must carry the incident byte")
            with self.assertRaises(UnicodeDecodeError):
                path.read_text(encoding="cp1252")
            self.assertIn("hello", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
