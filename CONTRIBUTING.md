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

People outside this repository whose reports changed the code, every one of them, oldest first.
Nine reports from two people, and every closed one of them landed a fix.

<!-- Add a row when the fix lands, never when the report arrives: the credit names a change.
     Retroactive: every outside report that changed this code is listed, not only recent ones. -->

| report | who | what they found |
| --- | --- | --- |
| [#2](https://github.com/Clear-Sights/Makoto/issues/2) | [@AliceLJY](https://github.com/AliceLJY) | `gate.completion` false-positive: a file produced remotely over ssh and landed by `git pull` read as an unproduced claim. |
| [#10](https://github.com/Clear-Sights/Makoto/issues/10) | [@AliceLJY](https://github.com/AliceLJY) | `_DESTRUCTIVE_RX` false-positive on read-only `dd if=`, and the mirror miss of `of=`-first writes. |
| [#14](https://github.com/Clear-Sights/Makoto/issues/14) | [@AliceLJY](https://github.com/AliceLJY) | `_DISABLE_RX` false-positive on a lowercase `dd skip=` argument -- the sibling of #10. |
| [#15](https://github.com/Clear-Sights/Makoto/issues/15) | [@AliceLJY](https://github.com/AliceLJY) | A denylist audit naming a whole family of over- and under-matches, several BLOCK-level, with the shared root: the atoms scan the raw command string instead of parsing argv, quotes and comments. |
| [#17](https://github.com/Clear-Sights/Makoto/issues/17) | [@AliceLJY](https://github.com/AliceLJY) | `canon.recur` false-positive: Pre/Post pairing breaks when the harness injects dunder keys. |
| [#19](https://github.com/Clear-Sights/Makoto/issues/19) | [@tkulczy2](https://github.com/tkulczy2) | `_dispatch` rejected a camelCase `hookEventName` as `unknown_event` and exited 2, so Cursor-shaped sessions misrouted. |
| [#20](https://github.com/Clear-Sights/Makoto/issues/20) | [@tkulczy2](https://github.com/tkulczy2) | `makoto uninstall` reported `"unwired": true` unconditionally, and silently removed nothing. |
| [#28](https://github.com/Clear-Sights/Makoto/issues/28) | [@AliceLJY](https://github.com/AliceLJY) | `canon.recur` fired on transient failures and re-fired every Stop, because failed calls carry no PostToolUse. |
| [#45](https://github.com/Clear-Sights/Makoto/issues/45) | [@AliceLJY](https://github.com/AliceLJY) | `_ACK_RX` anchored at offset 0 of the whole user turn, so prepended Stop-hook feedback made `release.operator` -- the only discharge that gate honors -- unreachable exactly when it was needed. And the deeper one they filed as secondary: every canon atom is an existential over the whole session, so a fingerprint that has matched can never stop matching, which is what forces a human. That half is still open. |

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
