# CHAIN-FORMAT v1 -- the receipt substrate

The hash-chained, append-only format `ledger.py` writes to and `verify_chain` reads back. This is
what makes a `makoto receipt` claim independently re-checkable rather than merely asserted: every
row's `row_hash` binds it to everything before it, so a hand-edited row anywhere in the chain is
detectable, not just assumed absent.

## Row shape

```json
{"kind": "testrun", "key": "tests/x.py", "value": "3 passed in 0.1s", "exit": 0,
 "session_id": "vec", "ts": "2026-07-07T00:00:01Z", "status": "open", "src": "makoto",
 "prev_hash": "", "row_hash": "670b3702b24c394c3b705564667b5d05a09fa6378d7f09d76f29ec914a652c8b"}
```

- `kind` (str, required) -- see Epistemic tiers below.
- `key`, `value`, `session_id`, `ts`, `status`, and any kind-specific fields -- free-form,
  producer-defined per `kind`.
- `src` (str) -- the producer's own name. Absent `src` on a row means makoto-legacy (every row
  appended before this field existed -- only makoto has ever written to the chain).
- `prev_hash` (str) -- the chain's own previous `row_hash`, or `""` for the genesis row.
- `row_hash` (str) -- sealed per the hash recipe below. Computed by the writer, never trusted
  from a reader's own recomputation of someone else's claimed value -- a reader always
  re-derives it.

## Hash recipe (exact, must byte-match any reimplementation)

```
canonical(row)  = json.dumps({k: v for k, v in row.items() if k != "row_hash"},
                              sort_keys=True, ensure_ascii=False, separators=(",", ":"))
norm_sha256(s)  = sha256("\n".join(line.rstrip() for line in s.splitlines()).encode("utf-8")).hexdigest()
row_hash        = norm_sha256(prev_hash + canonical(row))
```

`row_hash` is EXCLUDED from `canonical()` (a row cannot hash its own hash); `prev_hash` is
INCLUDED (the link binds to chain position, not just content). `norm_sha256`'s per-line-rstrip
normalization means a reformat that changes only trailing whitespace hashes identically; an
internal-whitespace change does not.

## Storage

- State home: `$MAKOTO_STATE_DIR` env var, default `$HOME/.claude/makoto_state`.
- Stream file: `<state_dir>/chain.jsonl` -- one JSON object per line, append-only, never
  rewritten.
- Lock: an exclusive `fcntl.flock` on `<state_dir>/<name>.lock` (content-free sidecar), held
  across the WHOLE append (tail-read + write) so a concurrent append can never fork the chain.

## Verification

Re-walk the stream from the start, recomputing each row's expected `prev_hash`/`row_hash`.
Returns `None` when every link verifies (including the vacuously-intact absent/empty stream),
else the 0-based index of the FIRST row that fails to parse, is not a dict, or whose link does
not match. NEVER RAISES -- an unreadable store reads as `None` (vacuously clean): absent state
is not evidence of tampering.

## Epistemic tiers (who may write which `kind`)

- **Judgment kinds** -- `verdict`, `certified-fact`, `exemption`, `release.operator`, `audit`:
  an integrity faculty's own conclusion about the session. Makoto-only. A reader MUST NOT treat
  a judgment-kind row from any other `src` as authoritative. `release.operator` (2026-07-08) is
  the current canonical name for an operator-attributed discharge of a session-level finding;
  its legacy name `ack-block` is a permanent alias -- a reader encountering either kind string
  treats it identically. A future `release.green` kind (world-verified, agent-earnable
  discharge) is a distinct, not-yet-built sibling in the same `release` family, not a synonym
  for `release.operator`.
- **Observation kinds** -- `testrun`, `touched`, `fetch`, `value`: a raw recorded fact, no
  judgment attached. A reader that injects a chain-derived fact into agent-visible text MUST
  cite its `src` in the injected text ("chain-verified, recorded by makoto" vs. an unqualified
  guess) -- provenance is never silently laundered into an unqualified claim.

## Golden vectors

`tests/vectors/chain_v1/intact.jsonl` and `tests/vectors/chain_v1/tampered.jsonl` -- three fixed
rows (kinds `testrun`/`verdict`/`touched`), generated once by this spec's reference
implementation (`ledger.py`) and frozen byte-for-byte. `tampered.jsonl` is `intact.jsonl` with
row 1's `value` hand-edited to `"TAMPERED"`, its `row_hash` left stale. The suite asserts:
- `verify(intact.jsonl)` -> `None` (fully intact).
- `verify(tampered.jsonl)` -> `1` (the exact 0-based index of the broken row).
- `read(intact.jsonl)` -> exactly 3 rows, in file order, each with its documented `kind`/`key`.

Regenerating the vectors (only on a deliberate format change, never casually) means re-running
the reference implementation and re-freezing both files.
