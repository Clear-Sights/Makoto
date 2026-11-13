# AMEND_2: the comparison arm is 6.2.1, since 6.2.2 did not ship. Committed before any run; never edited after.

- **Finding:** `research/v622/RESULTS.md`. 6.2.2 failed its ship rule in all four cells, so 6.2.1 remains what is shipped (main 25adb83).
- **Arms:** plain, 6.2.1 and collect. Collect is as built: PR #185 at 01b4901, which contains 6.2.2's note from the tree.
- **Ship rule:** collect ships when both of these hold in each of the four cells:
  - it passes at least 6.2.1's count minus 4;
  - its cost ratio to plain is below 6.2.1's.
- **Predictions:** unchanged. I7 now reads against 6.2.1.
- **Harness:** `harness/live_collect.py` is 6.2.2's harness with the arm renamed, and `MAKOTO_SRT` passed through. `harness/analyze_collect.py` is 6.2.2's with this rule.
