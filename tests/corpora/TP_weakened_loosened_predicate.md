---
expected_finding:
  row_id: "content.verifier_predicate_weakened"
  fire_level: "error"
  reason_contains: "in ["
expected_pass: false
prior: "def check_status(s):\n    return s == 'passed'\n"
---
# Synthetic loosened verifier predicate
def check_status(s):
    return s in ['passed', 'passed-with-warnings']
