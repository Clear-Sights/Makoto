"""Sentinels for dropped_gate — a forward claim carrying identifying info (count / line-range
/ named symbol / named artifact) ✗ undischarged at turn-end. Ported from the validated
standalone build (/tmp dropped anchor: 9 sentinels + 3 teeth, dogfood 1 genuine fire/1426).
TP fires + adversarial near-miss TNs (discharged / vague / negated / count-met) stay silent;
neutering dropped_gate reddens the TP tests (falsify teeth).
"""
from makoto.checks.silentlyDroppedCommitment import dropped_gate


def _call(text, *, touched=(), reads=None):
    reads = reads or {}
    return dropped_gate(
        text, touched_keys=set(touched),
        fs_exists=lambda p: False,
        fs_size=lambda p: None,
        fs_read=lambda p: reads.get(p),
        empty_keys=set(),
    )


def test_tp_count_drop():
    f = _call("I will add 3 helper functions to utils.py")
    assert f is not None and f.pattern_id == "gate.dropped"


def test_tn_count_discharged():
    body = "def a():\n    pass\ndef b():\n    pass\ndef c():\n    pass\n"
    assert _call("I will add 3 helper functions to utils.py", reads={"utils.py": body}) is None


def test_tn_count_short_fires():
    # claimed 3, only 2 present -> still dropped
    body = "def a():\n    pass\ndef b():\n    pass\n"
    assert _call("I will add 3 helper functions to utils.py", reads={"utils.py": body}) is not None


def test_tp_artifact_drop():
    assert _call("Let me create config.yaml") is not None


def test_tn_artifact_discharged_by_touch():
    assert _call("Let me create config.yaml", touched={"config.yaml"}) is None


def test_tp_symbol_drop():
    assert _call("I will add def validate_seal to gates.py") is not None


def test_tn_symbol_discharged():
    body = "def validate_seal():\n    return True\n"
    assert _call("I will add def validate_seal to gates.py", reads={"gates.py": body}) is None


def test_tp_line_range_drop():
    assert _call("I will edit lines 10-20 of parser.py") is not None


def test_tn_line_range_discharged_by_touch():
    assert _call("I will edit lines 10-20 of parser.py", touched={"parser.py"}) is None


def test_tn_vague_promise_silent():
    assert _call("I will look into the parser and figure out what is going on") is None


def test_tn_negated_frame_silent():
    assert _call("I will never add config.yaml — there is no need for it") is None


def test_tn_tests_count_met():
    body = "def test_a():\n    pass\ndef test_b():\n    pass\n"
    assert _call("I will write 2 tests in test_x.py", reads={"test_x.py": body}) is None


def test_empty_silent():
    assert _call("") is None


def test_tn_count_discharged_by_lambda_helpers():
    # FP fix: a "create N helper functions" count-claim is satisfied by lambda-bound helpers, not
    # only `def`. The def-only counter saw 0 and false-fired; the widened counter sees 3 -> silent.
    body = "build = lambda x: x\nparse = lambda y: y\nfmt = lambda z: z\n"
    assert _call("I'll create 3 helper functions in utils.py", reads={"utils.py": body}) is None


def test_tn_count_discharged_by_arrow_consts():
    # JS arrow-const callables also discharge a count-claim.
    body = "const f = () => 1\nconst g = (a) => a\nconst h = x => x\n"
    assert _call("I'll create 3 helper functions in utils.js", reads={"utils.js": body}) is None


def test_tn_count_discharged_by_partials():
    # functools.partial-bound callables also discharge a count-claim.
    body = "add1 = partial(add, 1)\nadd2 = partial(add, 2)\nadd3 = functools.partial(add, 3)\n"
    assert _call("I'll create 3 helper functions in utils.py", reads={"utils.py": body}) is None


def test_tp_count_zero_callables_still_fires():
    # TP intact: claim N callables, file has 0 of ANY callable form (plain data) -> still fires.
    body = "x = 1\ny = 2\nz = 'hi'\n"
    assert _call("I'll create 3 helper functions in utils.py", reads={"utils.py": body}) is not None


def test_tp_count_short_lambda_still_fires():
    # TP intact: claimed 3, only 1 lambda present -> still fires.
    body = "go = lambda: 1\nx = 2\n"
    assert _call("I'll create 3 helper functions in utils.py", reads={"utils.py": body}) is not None


def test_optional_fs_callbacks_none_is_safe():
    # fs_exists/fs_size/fs_read are optional by signature (default None). A caller that omits them
    # must not crash the Stop hot path. The `... if fs_read is not None and path else None` /
    # `... if fs_size and path else None` guards are load-bearing: flipping either `and` to `or`
    # calls None(path) -> TypeError. This pins the optional-callback contract (sole killer of both).
    f = dropped_gate("I'll add a function foo to bar.py", touched_keys=set(),
                     fs_exists=None, fs_size=None, fs_read=None, empty_keys=set())
    assert f is not None and f.pattern_id == "gate.dropped"   # undischarged -> fires, no crash
