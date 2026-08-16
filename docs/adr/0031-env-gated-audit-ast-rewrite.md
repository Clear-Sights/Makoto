# 0031: Env-gated-audit detection moved from regex to active-code AST

Date: 2026-06-02

## Relocated design history

From `makoto/checks/envGatedAudit.py`'s module docstring:

```text
Why AST, not the old string matcher (cert 2026-06-02, warning-tier-elimination:43, which CUT the
prior ``regex_file_predicate``): the old regex (1) fired on MENTIONS in comments/strings/docs
(instance-vs-mention FP) — it even targeted ``.md``, firing on CLAUDE.md describing the shape;
(2) required a literal ``AUDIT`` in the var NAME (its ``body_rx``), a flat FN on a BODY-only
signal like ``if os.environ.get("MAKOTO_SHADOW"): run_integrity_check()``; (3) matched only
``os.environ.get(`` — ``os.getenv()`` was a flat FN. The active-code AST gate
(``substrate.factories.parse_introduced``) dissolves (1) — a comment / ``str`` Constant / docstring is
never a real ``ast.If``; checking the gated BODY's code identifiers (not just the var name)
dissolves (2); ``callee_chain`` matching both call forms + the subscript form dissolves (3).
```
