# 0021: Check result-shape law

Date: 2026-08-16

## Relocated design history

From `Check` in `makoto/registry.py`:

```text
`tests` declares the check's result/evidence shape (one of `TESTS_SHAPES`). The sibling
tests/test_check_law_tests.py rejects both an undeclared shape and a declaration whose
module/factory does not use that shape's required evidence primitive. Genuine one-offs keep
the empty default only when their id and reason are registered explicitly in that law.
```
