"""The register-line evaluator: one plant per operator (a case that must hold and its neighbour
that must not), and a fixture register of lines in the v9 shape. The lines are data; nothing
here is a per-entry check. Named-set tables are fixtures with placeholder words."""
import pytest

from makoto.substrate import line as L

NAMED = {"TEST_PATH": frozenset({r"(^|/)tests?/", r"(^|/)test_[^/]*\.py$"}),
         "DOC_PATH": frozenset({r"\.md$"}),
         "WAIVER": frozenset({r"#\s*hush\b"}),
         "SUPPRESS": frozenset({r"#\s*quiet\b"})}


def ev(**kw):
    kw.setdefault("event", "Pre")
    kw.setdefault("tool", "Bash")
    return kw


@pytest.mark.parametrize("text, fact, want", [
    ('tool=Bash', ev(), True),
    ('tool=Bash', ev(tool="Read"), False),
    ('tool!=Bash', ev(tool="Read"), True),
    ('tool!=Bash', ev(), False),
    ('tool in {Write,Edit}', ev(tool="Edit"), True),
    ('tool in {Write,Edit}', ev(), False),
    ('args.command matches "git\\s+push"', ev(args={"command": "git  push origin"}), True),
    ('args.command matches "git\\s+push"', ev(args={"command": "git pull"}), False),
    ('path matches TEST_PATH', ev(path="pkg/tests/a.py"), True),
    ('path matches TEST_PATH', ev(path="pkg/a.py"), False),
    ('exit>=1', ev(exit=2), True),
    ('exit>=1', ev(exit=0), False),
    ('exit>=2', ev(exit=2), True),
    ('exit<=2', ev(exit=2), True),
    ('exit<=0', ev(exit=0), True),
    ('exit<=0', ev(exit=1), False),
    ('not tool=Bash', ev(tool="Read"), True),
    ('not tool=Bash', ev(), False),
    ('tool=Bash and event=Pre', ev(), True),
    ('tool=Bash and event=Stop', ev(), False),
    ('tool=Read or event=Pre', ev(), True),
    ('tool=Read or event=Stop', ev(), False),
    ('not (tool=Read or event=Stop)', ev(), True),
    ('args.missing=x', ev(), False),
    ('args.missing!=x', ev(), True),
])
def test_each_operator_holds_on_its_case_and_not_on_its_neighbour(text, fact, want):
    assert L.holds(text, fact, [], NAMED) is want


def test_seen_reads_the_record_and_dollar_names_the_current_event():
    rec = [ev(args={"command": "make"}, exit=2), ev(args={"command": "ls"}, exit=0)]
    text = 'seen(args.command=$args.command and exit!=0)'
    assert L.holds(text, ev(args={"command": "make"}), rec, NAMED)
    assert not L.holds(text, ev(args={"command": "ls"}), rec, NAMED)
    assert not L.holds(text, ev(args={"command": "make"}), [], NAMED)


def test_unseen_since_counts_only_after_the_last_reset():
    text = 'unseen_since(tool=Write, args.command=$args.command)'
    cur = ev(args={"command": "make"})
    assert L.holds(text, cur, [ev(tool="Write"), ev(args={"command": "make"})], NAMED)
    assert not L.holds(text, cur, [ev(args={"command": "make"}), ev(tool="Write")], NAMED)
    assert not L.holds(text, cur, [ev(tool="Write")], NAMED)       # no reset: the whole record


def test_verifier_is_a_command_that_has_exited_nonzero():
    rec = [ev(args={"command": "pytest"}, exit=1)]
    assert L.holds("verifier", ev(args={"command": "pytest"}, exit=0), rec, NAMED)
    assert not L.holds("verifier", ev(args={"command": "ls"}, exit=0), rec, NAMED)


def test_tree_exists_reads_the_disk_under_the_event_cwd(tmp_path):
    (tmp_path / "out.txt").write_text("x")
    text = "tree.$claim.subject.exists"
    assert L.holds(text, ev(cwd=str(tmp_path), claim={"subject": "out.txt"}), [], NAMED)
    assert not L.holds(text, ev(cwd=str(tmp_path), claim={"subject": "gone.txt"}), [], NAMED)


def test_a_recorded_value_matches_literally_not_as_a_pattern():
    text = "seen(output matches $claim.subject)"
    assert L.holds(text, ev(claim={"subject": "a+b.txt"}), [ev(output="wrote a+b.txt")], NAMED)
    assert not L.holds(text, ev(claim={"subject": "a.b.txt"}), [ev(output="wrote axb.txt")], NAMED)


def test_an_unbound_name_is_not_evaluable_never_silently_false():
    with pytest.raises(L.Unbound):
        L.holds("args.command=$item", ev(args={"command": "x"}), [], NAMED)


@pytest.mark.parametrize("text", ['tool=', 'tool ~ Bash', 'seen(tool=Bash', 'path matches NOPE', 'tool=Bash and'])
def test_a_line_outside_the_language_is_refused(text):
    with pytest.raises(L.Malformed):
        L.parse(text, NAMED)


def test_lines_equal_up_to_order_share_one_canonical_form():
    a = 'tool=Bash and event=Pre and not (exit=0 or exit=1)'
    b = 'not (exit=1 or exit=0) and event=Pre and tool=Bash'
    assert L.canonical(a, NAMED) == L.canonical(b, NAMED)
    assert L.canonical(a, NAMED) != L.canonical('tool=Bash and event=Stop', NAMED)
    assert L.parse(L.canonical(a, NAMED), NAMED)                    # the canonical form parses back


# A fixture register in the v9 shape: each line is one entry's whole set.
REGISTER = {
    "retry": 'event=Pre and seen(args.command=$args.command and exit!=0) and tool=Bash '
             'and unseen_since(tool in {Write,Edit}, args.command=$args.command)',
    "hollow": 'event=Pre and not args.content matches "\\b(assert|raise|expect)" and path matches TEST_PATH '
              'and tool in {Write,Edit}',
    "waiver": 'args.content matches WAIVER and event=Pre and not args.content matches "\\b(until|expires)\\b" '
              'and tool in {Write,Edit}',
}


def test_the_fixture_register_fires_each_line_on_its_set_and_nowhere_else():
    failed = ev(args={"command": "make"}, exit=2)
    assert L.holds(REGISTER["retry"], ev(args={"command": "make"}), [failed], NAMED)
    assert not L.holds(REGISTER["retry"], ev(args={"command": "make"}), [failed, ev(tool="Edit")], NAMED)
    w = ev(tool="Write", path="tests/test_a.py", args={"content": "def test_a():\n    pass\n"})
    assert L.holds(REGISTER["hollow"], w, [], NAMED)
    assert not L.holds(REGISTER["hollow"], dict(w, args={"content": "def test_a():\n    assert f()\n"}), [], NAMED)
    assert not L.holds(REGISTER["hollow"], dict(w, path="src/a.py"), [], NAMED)
    x = ev(tool="Edit", args={"content": "y = f()  # hush"})
    assert L.holds(REGISTER["waiver"], x, [], NAMED)
    assert not L.holds(REGISTER["waiver"], dict(x, args={"content": "y = f()  # hush until the 3.5 release"}), [], NAMED)
