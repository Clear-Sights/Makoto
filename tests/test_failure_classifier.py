"""Tests for makoto.checks._failureClassifier -- D1's transient-vs-deterministic gold set.
Matches Task 1's own rigor bar: every marker class gets a real, named fixture, and the
fail-toward-uncertain contract is tested directly (never a guess on ambiguous input).
"""
from __future__ import annotations

from makoto.checks._failureClassifier import classify_failure

# ---- deterministic gold (classify_failure must return True) ------------------------------------
DETERMINISTIC_GOLD = {
    "syntax_error": "  File \"a.py\", line 3\n    def f(:\nSyntaxError: invalid syntax",
    "file_not_found": "cat: missing.txt: No such file or directory",
    "permission_denied": "bash: /root/secret: Permission denied",
    "module_not_found": "ModuleNotFoundError: No module named 'flask'",
    "command_not_found": "zsh: command not found: fooify",
    "windows_not_recognized": "'fooify' is not recognized as an internal or external command",
    "name_error": "NameError: name 'undefined_var' is not defined",
}

# ---- transient gold (classify_failure must return False) ---------------------------------------
TRANSIENT_GOLD = {
    "connection_refused": "curl: (7) Failed to connect to host: Connection refused",
    "timeout": "requests.exceptions.ConnectTimeout: Connection timed out",
    "dns_failure": "Temporary failure in name resolution",
    "http_503": "HTTP/1.1 503 Service Unavailable",
    "http_429": "HTTP/1.1 429 Too Many Requests",
    "rate_limited": "Error: you have hit the rate limit, please slow down",
    "try_again_later": "Service busy, please try again in a few minutes",
    "still_running": "Job status: still running, check back later",
}

# ---- ambiguous gold (classify_failure must return None, never guess) --------------------------
AMBIGUOUS_GOLD = {
    "empty_string": "",
    "unrelated_success_text": "3 passed in 0.4s",
    "both_classes_present": "Permission denied -- retry after the rate limit resets",
    "generic_nonzero_exit_no_marker": "exit status 1",
}


def test_every_deterministic_gold_case_classifies_true():
    bad = {k: classify_failure(v) for k, v in DETERMINISTIC_GOLD.items() if classify_failure(v) is not True}
    assert not bad, f"deterministic gold misclassified: {bad}"


def test_every_transient_gold_case_classifies_false():
    bad = {k: classify_failure(v) for k, v in TRANSIENT_GOLD.items() if classify_failure(v) is not False}
    assert not bad, f"transient gold misclassified: {bad}"


def test_every_ambiguous_gold_case_classifies_none():
    bad = {k: classify_failure(v) for k, v in AMBIGUOUS_GOLD.items() if classify_failure(v) is not None}
    assert not bad, f"ambiguous gold wrongly resolved (must stay None): {bad}"


def test_none_input_is_uncertain_not_an_error():
    assert classify_failure(None) is None
