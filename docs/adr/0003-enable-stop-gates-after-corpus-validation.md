# 0003. Enable Stop gates after corpus validation

## Status

Accepted.

## Decision and context

Both Stop gates block live by default and are governed by one switch:

- completion: `UNFULFILLED`, where X was claimed produced but X is absent;
- advance: `SELF-CONTRADICTING`, where universal completion was claimed over an undischarged commitment.

Each was validated false-positive-clean on the 1,335-session honest corpus. For completion, production-claim binding drove worst-case false positives from 9.00% to a self-healing 2.42%, with true positives intact at 6/6 and the contamination canary passing.

Advance flipped live on 2026-06-01 after recording zero fires across all 1,335 sessions with the proposal-menu, code-fence, and optional-parenthetical sourcing guards. Every residual false positive had traced to a never-built proposal the AI recommended, never a genuine commitment; genuine commitments discharged when their files were touched. True-positive behavior remained intact: an undischarged firm promise plus universal-done still fires. The reason-bound retraction path clears legitimately dropped promises so honest reprioritization does not false-block.

`MAKOTO_DISABLE_GATES=1` returns both gates to shadow mode, still audited but not blocking. It is the single escape valve if a real-session false block surfaces.
