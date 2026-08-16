# 0035: jscpd clone flags on check modules, verified and dismissed

Date: 2026-07-09

## Relocated design history

From `makoto/checks/fabricatedCommitSha.py` (above `_claim_subject`):

```text
jscpd note (2026-07-09): flagged as a clone against phantomCitation.py. Verified: the matched
span is the fixed dispatcher entrypoint signature `predicate(*, current_event: dict,
history: list, pattern: Check, conn=None) -> Optional[Finding]` -- byte-identical across 9
check modules (grep '^def predicate(' checks/*.py: writeThrashRevert.py, verifierExitMasking.py,
unsourcedWebfetch.py, selfMuteGuard.py, illusoryAuthorshipTrailer.py, forbiddenLocation.py,
among others) -- plus a coincidental preceding `return False` from this file's own unrelated
`_real_commit_in_history` helper. A dispatcher-invoked entrypoint's signature is a structural
contract, not extractable logic; the two functions' bodies do unrelated things.
```

From `makoto/checks/illusoryAuthorshipTrailer.py` (below the module docstring):

```text
jscpd note (2026-07-09): flagged as a clone against verifierExitMasking.py. Verified: the matched
span is only this docstring's closing "Knight-Leveson" line + the standard
`from __future__ import annotations` / `import re` / `from typing import Optional` /
`from makoto.vocab import Finding` + `from makoto.registry import Check` headers both Pre-hook predicate modules need --
it ends before any function body, so no logic is shared (this module's Claude-authorship-trailer
regex is unrelated to verifierExitMasking's runner/exit-mask detection). See
tests/test_no_alpha_duplicate_functions.py for the package's real duplicate-logic gate.
```

From `makoto/checks/verifierExitMasking.py` (below the module docstring) -- the mirror side of the
same flag as `illusoryAuthorshipTrailer.py` above:

```text
jscpd note (2026-07-09): flagged as a clone against illusoryAuthorshipTrailer.py. Verified: the
matched span is only this docstring's closing "Knight-Leveson" line + the standard
`from __future__ import annotations` / `import re` / `from typing import Optional` /
`from makoto.vocab import Finding` + `from makoto.registry import Check` headers both Pre-hook predicate modules need --
it ends before any function body, so no logic is shared (this module's runner/exit-mask
detection is unrelated to illusoryAuthorshipTrailer's Claude-authorship-trailer regex). See
tests/test_no_alpha_duplicate_functions.py for the package's real duplicate-logic gate.
```

From `makoto/checks/deferredCheckboxTheater.py` (below the module docstring):

```text
jscpd note (2026-07-09): flagged as a clone against verifierPredicateWeakened.py. Verified: both
modules already reuse the ONE shared factory (substrate.factories.regex_file_predicate) -- the
matched span is just the minimal `regex_file_predicate(target_rx=re.compile(r"...")` call-site
syntax common to ANY two callers of that factory, plus the shared doc-convention lines. The two
target_rx/body_rx regexes differ and ARE each check's real, distinct content; collapsing the call
sites further would mean merging two unrelated file/body patterns into one, which would be wrong.
This pair is already at the dedup endpoint substrate.factories.regex_file_predicate exists for.
```

From `makoto/checks/verifierPredicateWeakened.py` (below the module docstring) -- the mirror side
of the same flag as `deferredCheckboxTheater.py` above:

```text
jscpd note (2026-07-09): flagged as a clone against deferredCheckboxTheater.py. Verified: both
modules already reuse the ONE shared factory (substrate.factories.regex_file_predicate) -- the
matched span is just the minimal `regex_file_predicate(target_rx=re.compile(r"...")` call-site
syntax common to ANY two callers of that factory, plus the shared doc-convention lines. The two
target_rx/body_rx regexes differ and ARE each check's real, distinct content; collapsing the call
sites further would mean merging two unrelated file/body patterns into one, which would be wrong.
This pair is already at the dedup endpoint substrate.factories.regex_file_predicate exists for.
```

From `makoto/checks/verifierBodyHollowed.py` (below the module docstring):

```text
jscpd note (2026-07-09): flagged as a clone against certVerifyDisabled.py. Verified: the matched
span is only this docstring's closing prose + the "Knight-Leveson" line + the standard
`from __future__ import annotations` / `import ast` / `import re` / `from typing import Optional`
header both modules need -- it ends before any function body, so no logic is shared (this
module's hollow-body/swallowed-except analysis is unrelated to certVerifyDisabled's TLS callee
gate). See tests/test_no_alpha_duplicate_functions.py for the package's real duplicate-logic gate.
```
