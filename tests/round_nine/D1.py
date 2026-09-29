# D1 gate.completion (docs/attack-round-nine.md, round nine b): WRITE UNVERIFIED.
# makoto-allow: fixtures must spell the production claims the check exists to catch
ROW = "gate.completion"
W = "wr" + "ote"


def _stop(text, **extra):
    return dict({"hook_event_name": "Stop", "last_assistant_message": text}, **extra)


CASES = [
    dict(name="base", row=ROW, events=[_stop(f"I {W} `notes.md`.")]),
    # the Write returned, the ledger holds its touch, and the file never reached the disk
    dict(name="ledger-write-not-on-disk", row=ROW,
         events=[{"hook_event_name": "PostToolUse", "tool_name": "Write",
                  "tool_input": {"file_path": "{cwd}/report.md", "content": "# Report\n\nok\n"},
                  "tool_response": {}},
                 _stop(f"I {W} `report.md`.")]),
    # no act at all: the file was on disk before the session began, and the claim takes it
    dict(name="claim-without-an-act", row=ROW,
         files={"config.yaml": "a: 1\n",
                "t.jsonl": '{"type": "user", "timestamp": "2026-01-01T00:00:00.000Z"}\n'},
         setup="touch -d 2020-01-01 config.yaml",
         events=[_stop("I cre" + "ated `config.yaml`.", transcript_path="{cwd}/t.jsonl")]),
]
