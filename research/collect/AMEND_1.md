# AMEND_1: no outward-library gate; the sandbox is the gate. Committed before any code is measured and before any run; never edited after.

Owner, 2026-11-13: "it can run whatever it needs whether it reaches the net or not, as it's in a sandbox".

## Change to RULES.md
- **Every runnable entry program is probed,** whatever it imports. The outward-library list of `research/set_probe/AMEND_1.md` is not used, and no such list is in the code.
- **Safety is the sandbox's:** no network, and no write outside the copy.
- **Accuracy:** a program that needs the network fails in the sandbox. A failure's message therefore ends: "(run in a sandbox with no network)". The hold still blocks once only.
- **Tests:**
  - the test "a program that reaches `subprocess` is not probed" is replaced by "a program that imports `subprocess` or `socket` is probed";
  - a probe that fails for want of the network gives the message with that ending.
- **Unchanged:** everything else in RULES.md.
