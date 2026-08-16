# 0026: gate.liveness uses the canonical makoto-allow marker predicate

## Relocated design history

From `analyze_file._allowed()` in `deadPureStatement.py`:

```text
Was a bare `"makoto-allow" in line` substring test, which exempted a reasonless `# makoto-allow`
that `makoto_allowed`/`_MAKOTO_ALLOW_RX` rejects — and that this check's own finding text already
tells the author to write with a reason.
```

The current rule and its safety rationale — the exemption goes through the ONE canonical marker
predicate (§7.5b), because an exemption marker asserts an audit trail and accepting one without a
rationale accepts the assertion unmeasured — stays in the source comment.
