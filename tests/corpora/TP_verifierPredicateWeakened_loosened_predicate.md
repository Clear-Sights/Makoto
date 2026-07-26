---
expected_finding:
  row_id: "content.verifier_predicate_weakened"
  fire_level: "error"
  reason_contains: "in ["
expected_pass: false
---
# Synthetic loosened verifier predicate
def check_status(s):
    return s in ['passed', 'passed-with-warnings']
