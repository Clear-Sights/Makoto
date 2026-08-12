# Self-wiring: current scope and blind spot

Makoto can observe a project settings change and report that its own hook wiring was removed. It
does not claim to protect a project that was never wired, and it does not claim to survive a
simultaneous removal of every hook that would run the check.

## What is actually wired

The packaged hook manifest is [hooks.json](../hooks/hooks.json). The regular hook adapter is
[`makoto/_dispatch_shim.sh`](../makoto/_dispatch_shim.sh); ConfigChange uses
[`makoto/_dispatch_configchange_shim.sh`](../makoto/_dispatch_configchange_shim.sh). Both shims
refuse a missing plugin root with exit 2 instead of masking an unevaluable invocation as success.

The ordinary Stop-edge self-wiring signal is implemented by
[`makoto/checks/selfWiredCheck.py`](../makoto/checks/selfWiredCheck.py). It is advisory: a partial
strip can be recorded and surfaced without asserting that every unwired project is dishonest. The
separate ConfigChange adapter is
[`makoto/_dispatch_configchange.py`](../makoto/_dispatch_configchange.py), with verdict logic in
[`makoto/verdict/configchange_verdict.py`](../makoto/verdict/configchange_verdict.py).

The adapter blocks only when the stripped path has evidence that Makoto had previously wired it:
either the installer recorded that path in its manifest, or an earlier evaluation recorded a
had-hooks state. A first observation of an unwired path is not enough evidence to block. The two
tiers are exercised end-to-end in
[`tests/test_dispatch_configchange.py`](../tests/test_dispatch_configchange.py) and
[`tests/test_dispatch_configchange_blocking.py`](../tests/test_dispatch_configchange_blocking.py).

## The asymmetry that remains

The self-wiring check needs a live hook to run. Removing one hook while another remains lets the
remaining hook produce evidence. Removing every Makoto hook at once prevents any Makoto hook from
executing, so no in-process check can observe that change at the moment it happens. This is a
coverage boundary, not a claimed guarantee.

The practical response is external evidence: keep the canonical package manifest under review,
use the host's configuration history, and run the repository checks after wiring changes. Makoto's
own proof of the package-side wiring is in
[`tests/test_self_wired_check.py`](../tests/test_self_wired_check.py); it is not evidence that a
host delivered a hook event in a particular session.

## Why this replaces the old follow-up

The previous note described deleted module names and sibling-project paths as though they were
current sources. That made the document look more evidenced while making its citations impossible
to follow. This replacement names only current sources and leaves historical removals to the
[changelog](../CHANGELOG.md), where a removed path is a historical fact rather than a present
source citation.
