# 0023: canon's exit_code terminal reads exitCode

## Relocated design history

From `exit_code()` in `canonTimeoutRecur.py`:

```text
BUGFIX (this ticket): was reading the wrong key `"exit_code"` — the real substrate's Bash
tool_response carries it camelCase as `"exitCode"` (confirmed live-correct elsewhere:
makoto/ledger.py:49 and makoto/checks.py:124 both already read `tool_response["exitCode"]`).
This terminal was consequently dead code no installed primitive could ever observe firing
correctly; no live primitive reads it (see docstring above), so the fix changes no gate
behavior — only makes the terminal itself correct.
```
