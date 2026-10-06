"""Executable lifecycle decisions over the caller's current measurements."""

from collections.abc import Mapping


VALIDATE_JOBS = frozenset({'evaluate', 'observed', 'hook', 'package', 'audit'})
JOIN_INPUTS = frozenset({'register', 'validate', 'package', 'fresh', 'audit'})


def handoff(verdict):
    """Carry the current bounded verdict forward until its inputs change.

    Preserve explicit absences and external limitations supplied by the caller.
    No retained evidence, hooks, or outside operators are consulted. A changed
    input requires the caller to re-measure and re-derive dependency waves.
    """
    from copy import deepcopy

    if not isinstance(verdict, Mapping):
        raise TypeError('handoff requires a current verdict mapping')
    bundle = deepcopy(dict(verdict))
    bundle['wake'] = 'changed_input'
    return bundle


def join(head, inputs):
    """Join current passing measurements for the selected head.

    Missing, failed, malformed, or mismatched inputs leave completion open.
    Retained evidence files are never consulted.
    """
    done = (
        isinstance(head, str)
        and bool(head.strip())
        and isinstance(inputs, Mapping)
        and JOIN_INPUTS <= inputs.keys()
        and all(
            isinstance(inputs[name], Mapping)
            and inputs[name].get('head') == head
            and inputs[name].get('decision') == 'pass'
            for name in JOIN_INPUTS
        )
    )
    return {'decision': 'done' if done else 'not_done'}


def audit(root):
    """Scan current file bytes for credentials, including ignored content.

    Git metadata is excluded. This is a bounded credential scan, not a
    certificate of semantic liveness or of outside operator evidence.
    Unreadable files and symlinks reject rather than silently leaving gaps.
    Findings contain paths and categories, never credential values.
    """
    import hashlib
    import os
    from pathlib import Path
    import re

    source = Path(root).resolve(strict=True)
    if not source.is_dir():
        raise NotADirectoryError(source)
    patterns = {
        'aws_access_key': re.compile(rb'(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])'),
        'private_key': re.compile(rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
    }
    findings = []
    digest = hashlib.sha256()
    walk_errors = []
    for directory, directories, filenames in os.walk(
            source, followlinks=False, onerror=walk_errors.append):
        directories[:] = sorted(name for name in directories if name != '.git')
        for name in list(directories):
            path = Path(directory) / name
            if path.is_symlink():
                findings.append({'path': path.relative_to(source).as_posix(),
                                 'category': 'symlink'})
                directories.remove(name)
        for name in sorted(filenames):
            if name == '.git':
                continue
            path = Path(directory) / name
            relative = path.relative_to(source).as_posix()
            if path.is_symlink():
                findings.append({'path': relative, 'category': 'symlink'})
                continue
            try:
                data = path.read_bytes()
            except OSError:
                findings.append({'path': relative, 'category': 'unreadable'})
                continue
            encoded = relative.encode('utf-8', errors='surrogateescape')
            digest.update(len(encoded).to_bytes(8, 'big'))
            digest.update(encoded)
            digest.update(len(data).to_bytes(8, 'big'))
            digest.update(data)
            for category, pattern in patterns.items():
                if pattern.search(data):
                    findings.append({'path': relative, 'category': category})
    for error in walk_errors:
        findings.append({'path': os.path.relpath(error.filename, source),
                         'category': 'unreadable'})
    return {'decision': 'reject' if findings else 'clean',
            'input_digest': digest.hexdigest(), 'findings': findings}


def fresh(plugin, account, event):
    """Install current plugin bytes in a new account and execute its hook.

    Each call owns a fresh account directory and isolated hook state. The
    returned response is measured from the installed runtime, never a receipt.
    """
    import json
    import os
    from pathlib import Path
    import shutil
    import subprocess
    import sys

    source = Path(plugin).resolve(strict=True)
    if not (source / 'makoto2' / '__main__.py').is_file():
        raise FileNotFoundError(source / 'makoto2' / '__main__.py')
    raw = json.dumps(event, allow_nan=False)
    home = Path(account).resolve()
    # Refuse reused accounts so prior state cannot suppress a fresh finding.
    home.mkdir(parents=True, exist_ok=False)
    installed = home / '.claude' / 'plugins' / 'makoto2'
    package(source.parent, installed)
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    env.update(HOME=str(home), CLAUDE_PLUGIN_ROOT=str(installed),
               MAKOTO_STATE_DIR=str(home / '.claude' / 'makoto2_state'),
               PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run(
        [sys.executable, '-s', '-m', 'makoto2'], cwd=installed, env=env,
        input=raw, text=True, capture_output=True, check=True,
    )
    response = json.loads(result.stdout)
    if not isinstance(response, dict):
        raise ValueError('Installed hook did not return a response object')
    return response


def package(root, destination):
    """Build the current plugin artifact without consulting proof receipts."""
    from makoto2 import build_package
    return build_package(root, destination)


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
