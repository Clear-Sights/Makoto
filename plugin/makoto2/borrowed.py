"""Modified excerpts from DetIO and Causality; source pins in BORROWED.tsv.

Copyright 2026 Clear-Sights. Licensed under Apache-2.0 (LICENSE).
Changes: numeric leaves, explicit store, SHA verification, call-site traces.
"""
import hashlib
from pathlib import Path
import re


def leaves(r, path=()):
    """DetIO core.leaves: every string in a nested native response."""
    if isinstance(r, str):
        yield path, r
    elif type(r) in (int, float):
        yield path, str(r)
    for k, v in (r.items() if isinstance(r, dict) else enumerate(r) if isinstance(r, list) else ()):
        yield from leaves(v, path + (k,))


def get(store, address):
    """Adapted DetIO core.get: only a witnessed content address is opened."""
    if not re.fullmatch(r'[0-9a-f]{12}|[0-9a-f]{64}', address):
        raise ValueError('invalid DetIO address')
    data = (Path(store).expanduser() / 'objects' / address).read_bytes()
    if not hashlib.sha256(data).hexdigest().startswith(address):
        raise ValueError('DetIO object does not match its bytes')
    return data.decode('utf-8')


def receipt(claim, trace, fingerprint):
    # Causality receipt, copied unchanged; no trace-free admitted write.
    if not trace:
        raise ValueError("a claim without a trace is a belief, not a receipt")
    return {"claim": claim, "trace": trace, "instruments": fingerprint}


def fragments(value):
    """Tool input/response includes its literal field names as well as values."""
    yield from (v for _, v in leaves(value))
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            if isinstance(child, (dict, list)):
                yield from fragments(child)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, (dict, list)):
                yield from fragments(child)
