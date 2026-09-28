"""kit.neighbours and kit.claim, the two shared pieces docs/FOUNDATION-14.md builds first."""
from __future__ import annotations

import re
import time

from makoto.kit import claim, neighbours


def test_neighbours_one_token_changed_added_or_removed():
    cmds = ["pytest -q tests", "pytest -x tests", "pytest -q tests -k a", "pytest tests",
            "pytest -q tests", "ls"]
    got = neighbours(cmds)
    assert (0, 1) in got            # changed
    assert (0, 2) not in got        # two tokens added
    assert (0, 3) in got and (1, 3) in got   # removed
    assert (0, 4) not in got        # identical is not a neighbour
    assert all(5 not in p for p in got)
    assert neighbours(["git status", "git status -s"]) == [(0, 1)]   # the shorter one first
    assert neighbours(["a b", "a b", "a c"]) == [(0, 2), (1, 2)]     # repeats keep every index
    assert neighbours(["a a", "a"]) == [(0, 1)]                      # a repeated token deleted


def test_neighbours_refuses_other_k():
    import pytest
    with pytest.raises(ValueError):
        neighbours(["a"], k=2)


def _seconds(cmds):
    t = time.perf_counter()
    assert neighbours(cmds) == []
    return time.perf_counter() - t


def test_neighbours_is_not_quadratic():
    # ratios, never one mean against a bar: doubling the input may at most ~double the time
    distinct = lambda n: [f"cmd{i} a{i} b{i} c{i}" for i in range(n)]
    repeats = lambda n: ["pytest -q tests"] * n
    long = lambda n: [" ".join(f"t{i}" for i in range(n))]
    for make, n in ((distinct, 20000), (repeats, 4000), (long, 4000)):
        small, big = min(_seconds(make(n)) for _ in range(3)), min(_seconds(make(2 * n)) for _ in range(3))
        assert big < 3.2 * small + 0.02, (make.__name__, n, small, big)


def test_claim_skips_quoted_negated_and_forward_framed():
    rx = re.compile(r"\bis running\b")
    assert claim("The server is running now.", rx) is not None
    assert claim("The server `is running` there.", rx) is None
    assert claim("It is not clear it is running.", rx) is None
    assert claim("Once deployed, it is running.", rx) is None
    assert claim("", rx) is None
    assert claim("Output:\n```\nthe server is running", rx) is None   # unterminated fence


def test_neighbours_matches_the_pairwise_definition():
    import itertools
    import random

    def one_apart(x, y):
        if len(x) == len(y):
            return sum(a != b for a, b in zip(x, y)) == 1
        long, short = (x, y) if len(x) > len(y) else (y, x)
        return len(long) == len(short) + 1 and any(long[:p] + long[p + 1:] == short
                                                    for p in range(len(long)))
    r = random.Random(7)
    for _ in range(2000):
        cs = [" ".join(r.choice("abc") for _ in range(r.randint(0, 4))) for _ in range(r.randint(0, 9))]
        toks = [tuple(c.split()) for c in cs]
        want = [(i, j) for i, j in itertools.combinations(range(len(cs)), 2) if one_apart(toks[i], toks[j])]
        assert neighbours(cs) == want, cs
