# B9 gate.undischarged_waiver (docs/attack-round-nine.md, round nine b).
# makoto-allow: fixtures must spell the undischarged waivers the check exists to catch
ROW = "gate.undischarged_waiver"
H = "#"


def _write(path, content):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": path, "content": content}}


CASES = [
    dict(name="base", row=ROW, events=[_write("{cwd}/m.py", f"import os  {H} no" + "qa\n")]),
    dict(name="upper-noqa", row=ROW, events=[_write("{cwd}/m.py", f"import os  {H} NO" + "QA\n")]),
    dict(name="unittest-skip", row=ROW,
         events=[_write("{cwd}/test_m.py",
                        "import unittest\n\n\nclass T(unittest.TestCase):\n    @unittest.sk" + "ip\n"
                        "    def test_x(self):\n        self.assertTrue(False)\n")]),
]
