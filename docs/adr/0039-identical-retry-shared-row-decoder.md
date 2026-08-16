# 0039: identicalRetryInterdiction decodes history rows through the shared kit decoder

## Relocated design history

From `makoto/checks/identicalRetryInterdiction.py`'s `_most_recent_completed_bash_call()`:

```text
A hand-rolled local copy of this logic used to live here, justified as keeping "zero cross-module
coupling" with a module that ALREADY imports `bash_output_text` from the same kit two lines above
-- that claim was already false when it was written, and the drift it enabled was a real bug: this
predicate was blind to rows whose event type lives only on the WRAPPER column, rows its sibling
gate (canon.timeout/canon.recur) acts on, from the same table, for the same concept.
```
