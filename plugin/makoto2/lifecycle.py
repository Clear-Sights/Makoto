"""Executable lifecycle decisions over the caller's current measurements."""

from collections.abc import Mapping


VALIDATE_JOBS = frozenset({'evaluate', 'observed', 'hook', 'package', 'audit'})


def validate(head, jobs, *, local_pass):
    """Require a passing local suite and all CI jobs for the selected head.

    The caller supplies current job results; retained evidence files are not
    inputs to this decision. Missing or mismatched results fail closed.
    """
    passed = (
        isinstance(head, str)
        and bool(head.strip())
        and local_pass is True
        and isinstance(jobs, Mapping)
        and VALIDATE_JOBS <= jobs.keys()
        and all(
            isinstance(jobs[name], Mapping)
            and jobs[name].get('head') == head
            and jobs[name].get('result') == 'pass'
            for name in VALIDATE_JOBS
        )
    )
    return {'decision': 'pass' if passed else 'reject'}
