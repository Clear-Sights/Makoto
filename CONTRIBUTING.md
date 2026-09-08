# Contributing

Reports are welcome. Code is not merged from outside this repository.

That is a provenance rule, not a judgement about the contribution. Every line here carries a
claim about where it came from and what graded it — that is the same standard makoto applies to
an agent's own work, and it is the whole point of the tool. Code arriving from outside cannot
carry those claims, and I will not assert them on someone else's behalf. So the policy is stated
up front rather than discovered after the work is done.

## What is genuinely wanted

**Issues.** A defect report with a reproducer, a measurement, or a reading of the code is the
most useful thing anyone outside this repository can send, and it is acted on. The two most
valuable reports this project has received were exactly that: a precise reading of one regex and
its anchor, and a profile naming the hot path. Neither needed a diff to be worth acting on.

A good report has:

- **the artifact and line** — `plugin/makoto/state/ledger.py:511`, not "the ack regex"
- **what you observed**, and the command that produced it
- **what you expected instead**, and why the code says it should
- **the boundary** — where you stopped, and what you did not check

None of that is a template to fill in. A one-paragraph report naming a file and a line is more
useful than a long one that names neither.

## What happens to a report

The fix is written here, from the report and from this project's own measurements. If your
report names a defect, you are credited by name in the commit message and in the release note,
and listed below. If a pull request is opened, it is closed with thanks and the same credit — the
finding is what mattered, and closing the PR does not discard it.

## Acknowledgements

People outside this repository whose reports changed the code. Listed in the order received.

<!-- Add a row when the fix lands, never when the report arrives: the credit names a change. -->

| who | what they found | where it landed |
| --- | --- | --- |

## Checking something yourself

The gates are the same ones CI runs, and none of them need this repository's history:

```
python -m pip install -e . pytest
python3 tools/render_checks.py --check   # generated blocks match their sources
python -m pytest -q                      # the suite
python3 eval/replay.py                   # the authored sessions replay to their expectations
```

`eval/replay.py` is the one worth knowing about: it drives frozen sessions through the real
dispatcher and asserts each expectation, so it will tell you whether a change altered any
recorded outcome without your having to read the suite.

## Security

Do not open a public issue for a vulnerability. Use GitHub's private vulnerability reporting on
this repository instead.
