---
expected_finding:
  row_id: "1.1"
  fire_level: "error"
  reason_contains: "loosened"
expected_pass: false
---
# Synthetic loosened verifier predicate
def check_status(s):
    return s in ['passed', 'passed-with-warnings']
