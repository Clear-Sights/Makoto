"""lib/factories.py (L1) is the home for the predicate-factory + AST primitives. Importable under
the new path; L1 purity (imports only L0: schema, lexicons)."""
import ast
from pathlib import Path


def test_factories_exports_all_symbols():
    from makoto.lib import factories
    for name in ("regex_file_predicate", "ast_introduced_predicate", "scan_target_content",
                 "parse_introduced", "is_false_const", "is_cert_none", "callee_chain",
                 "makoto_allowed"):
        assert callable(getattr(factories, name)), name


def test_factories_is_L1_imports_only_L0():
    src = Path(__file__).resolve().parents[2] / "lib" / "factories.py"
    tree = ast.parse(src.read_text())
    allowed = {"makoto.schema", "makoto.lexicons"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("makoto"):
            assert node.module in allowed, f"L1 factories may import only L0: got {node.module}"


def test_makoto_allowed_structured_marker():
    from makoto.lib.factories import makoto_allowed
    assert makoto_allowed("x  # makoto-allow: legit reason") is True
    assert makoto_allowed("x  # makoto-allow") is False


# --- behavioral cases redistributed verbatim from the dissolved tests/predicates/test_helpers.py (idealization: name<->content) ---

def _pat(pid="X.Y", desc="test pattern"):
    from makoto.schema import PreCheck
    return PreCheck(
        id=pid, fire_level="error", description=desc,
        retry_hint="fix it",
    )


def _evt(file_path: str, content: str, event="PreToolUse") -> dict:
    return {"hook_event_name": event,
            "tool_input": {"file_path": file_path, "content": content}}


def test_regex_file_predicate_fires_when_body_matches_in_target_file():
    """factory: body regex hit on a path matching target regex -> Finding."""
    import re
    from makoto.lib.factories import regex_file_predicate
    pred = regex_file_predicate(
        target_rx=re.compile(r"\.py$"),
        body_rx=re.compile(r"startswith\("),
    )
    f = pred(current_event=_evt("foo.py", "x.startswith('ok')"),
             history=[], pattern=_pat(), conn=None)
    assert f is not None
    assert f.pattern_id == "X.Y"
    assert f.level == "error"
    assert "startswith" in f.message
    assert f.line == 1


def test_regex_file_predicate_silent_when_body_misses():
    """body regex no hit -> None."""
    import re
    from makoto.lib.factories import regex_file_predicate
    pred = regex_file_predicate(
        target_rx=re.compile(r"\.py$"),
        body_rx=re.compile(r"startswith\("),
    )
    assert pred(current_event=_evt("foo.py", "x == 'ok'"),
                history=[], pattern=_pat(), conn=None) is None


def test_regex_file_predicate_silent_when_target_path_misses():
    """target regex no hit -> None (gate on path)."""
    import re
    from makoto.lib.factories import regex_file_predicate
    pred = regex_file_predicate(
        target_rx=re.compile(r"\.py$"),
        body_rx=re.compile(r"startswith\("),
    )
    assert pred(current_event=_evt("foo.txt", "x.startswith('ok')"),
                history=[], pattern=_pat(), conn=None) is None


def test_regex_file_predicate_silent_on_non_pretooluse():
    """only fires on PreToolUse."""
    import re
    from makoto.lib.factories import regex_file_predicate
    pred = regex_file_predicate(
        target_rx=re.compile(r"\.py$"),
        body_rx=re.compile(r"startswith\("),
    )
    assert pred(current_event=_evt("foo.py", "x.startswith('ok')", event="Stop"),
                history=[], pattern=_pat(), conn=None) is None


def test_regex_file_predicate_finding_includes_line_number():
    """Finding.line is 1-indexed and points at the match line."""
    import re
    from makoto.lib.factories import regex_file_predicate
    pred = regex_file_predicate(
        target_rx=re.compile(r"\.py$"),
        body_rx=re.compile(r"BAD"),
    )
    content = "line1\nline2 BAD here\nline3"
    f = pred(current_event=_evt("foo.py", content),
             history=[], pattern=_pat(), conn=None)
    assert f is not None
    assert f.line == 2


def test_regex_file_predicate_finding_includes_snippet_context():
    """Finding.snippet contains ±40 chars of context."""
    import re
    from makoto.lib.factories import regex_file_predicate
    pred = regex_file_predicate(
        target_rx=re.compile(r"\.py$"),
        body_rx=re.compile(r"BAD"),
    )
    content = "leading context here " + "x" * 30 + "BAD" + "y" * 30 + " trailing context"
    f = pred(current_event=_evt("foo.py", content),
             history=[], pattern=_pat(), conn=None)
    assert f is not None
    assert "BAD" in f.snippet
    assert len(f.snippet) <= 40 + 3 + 40


def test_regex_file_predicate_exempt_rx_silences_and_labels_message():
    """factory: optional exempt_rx is a SECOND exemption (beyond makoto_allowed).

    This is the capability patterns 1.4/1.8 hand-rolled before being folded into the factory:
    fire iff (target ∧ body) AND NOT (makoto_allowed ∨ exempt_rx). When exempt_label is set, the
    fired message carries the ' with no <label>' suffix (so 1.4/1.8 keep their exact wording).
    """
    import re
    from makoto.lib.factories import regex_file_predicate
    pred = regex_file_predicate(
        target_rx=re.compile(r"\.toml$"),
        body_rx=re.compile(r"\w+_skip\s*=\s*true"),
        exempt_rx=re.compile(r"\bADR-\d+\b"),
        exempt_label="ADR backlink",
    )
    # flag present, NO exemption -> fires, message carries the label suffix
    f = pred(current_event=_evt("c.toml", "x_skip = true\n"),
             history=[], pattern=_pat(), conn=None)
    assert f is not None and "with no ADR backlink" in f.message
    # flag present BUT exemption (ADR backlink) present -> silent
    assert pred(current_event=_evt("c.toml", "x_skip = true  # ADR-042\n"),
                history=[], pattern=_pat(), conn=None) is None
    # back-compat: without exempt_rx, no suffix, still fires (existing 1.1/1.2/1.3/1.5 behavior)
    plain = regex_file_predicate(target_rx=re.compile(r"\.toml$"),
                                 body_rx=re.compile(r"\w+_skip\s*=\s*true"))
    g = plain(current_event=_evt("c.toml", "x_skip = true\n"),
              history=[], pattern=_pat(), conn=None)
    assert g is not None and "with no" not in g.message


def test_scan_target_content_non_dict_returns_empty_string():
    """L56 RETURN: non-dict tool_input -> '' (NOT None). A None return makes a
    downstream body_rx.search(None) raise TypeError; the contract is '' so the
    content-scan stays silent. Pins `return ""` against `return None`."""
    from makoto.lib.factories import scan_target_content
    assert scan_target_content("x") == ""
    assert scan_target_content([1, 2]) == ""


def test_scan_target_content_multiedit_skips_non_dict_edits():
    """L66 BOOL (and->or): the comprehension guard `isinstance(e, dict) and e.get(...)`
    must AND both — a non-dict edit element must be skipped, not have .get() called on
    it. Under `or`, the non-dict 'x' reaches e.get(...) and raises AttributeError.
    Pins the `and` in the edits comprehension filter."""
    from makoto.lib.factories import scan_target_content
    ti = {"edits": [{"new_string": "good"}, "x"]}
    assert scan_target_content(ti) == "good"


def test_scan_target_content_empty_dict_returns_empty_string():
    """L67 RETURN: a dict with no content/new_string/edits-list falls through to
    `return ""`. Mutating to `return None` would feed None to a downstream
    body_rx.search(None) (TypeError). Pins the final `return ""`."""
    import re
    from makoto.lib.factories import scan_target_content, regex_file_predicate
    assert scan_target_content({}) == ""
    assert scan_target_content({"edits": "notalist"}) == ""
    # downstream: with content '' the predicate is silent; with None it would TypeError
    pred = regex_file_predicate(target_rx=re.compile(r"\.py$"),
                                body_rx=re.compile(r"BAD"))
    evt = {"hook_event_name": "PreToolUse", "tool_input": {"file_path": "foo.py"}}
    assert pred(current_event=evt, history=[], pattern=_pat(), conn=None) is None


def test_parse_introduced_whitespace_only_is_unparsed():
    """L86 BOOL (or->and): `if not content or not content.strip()` must OR — a
    whitespace-only string is truthy but blank, so the strip() arm must still
    return (None, 0). Under `and`, '   ' falls through and parses to an empty
    ast.Module (non-None). Pins the `or` guard."""
    from makoto.lib.factories import parse_introduced
    tree, off = parse_introduced("   ")
    assert tree is None
    assert off == 0


def test_parse_introduced_empty_returns_none_sentinel():
    """L87 RETURN: empty content returns the (None, 0) sentinel that AST predicates
    test with `if tree is None`. Mutating the returned value (e.g. to (True, 0))
    makes tree[0] a non-None object, so a downstream ast.walk(tree) raises
    AttributeError instead of staying silent. Pins `return None, 0`."""
    from makoto.lib.factories import parse_introduced
    tree, off = parse_introduced("")
    assert tree is None
    assert off == 0


def _assign_ast_predicate():
    import ast
    import re
    from makoto.lib.factories import ast_introduced_predicate
    return ast_introduced_predicate(
        target_rx=re.compile(r"\.py$"),
        node_match=lambda node: "ASSIGN" if isinstance(node, ast.Assign) else None,
    )


def test_ast_introduced_predicate_snippet_is_actual_line():
    """L143 CMP (`0 < line_no <= len(lines)`): when line_no is in bounds the snippet
    is the real source line, NOT the str(label) fallback. Flipping the comparator
    (e.g. `0 >=`) sends an in-bounds line to the `str(label)` branch, so the snippet
    becomes 'ASSIGN' instead of 'x = 1'. Pins the bounds comparator."""
    pred = _assign_ast_predicate()
    evt = {"hook_event_name": "PreToolUse",
           "tool_input": {"file_path": "foo.py", "content": "x = 1"}}
    f = pred(current_event=evt, history=[], pattern=_pat(), conn=None)
    assert f is not None
    assert f.snippet == "x = 1"


def test_is_false_const_only_matches_literal_false():
    """is_false_const is True ONLY for the literal `False` constant — not True, not 0, not a Name."""
    import ast
    from makoto.lib.factories import is_false_const
    expr = lambda s: ast.parse(s, mode="eval").body
    assert is_false_const(expr("False")) is True
    assert is_false_const(expr("True")) is False
    assert is_false_const(expr("0")) is False           # 0 is falsy but not the False constant
    assert is_false_const(expr("x")) is False


def test_callee_chain_descends_intermediate_call():
    """callee_chain returns the dotted callee, descending through an intermediate Call so the
    library receiver token survives (`requests.Session().get` -> 'requests.Session.get')."""
    import ast
    from makoto.lib.factories import callee_chain
    call = lambda s: ast.parse(s, mode="eval").body
    assert callee_chain(call("jwt.decode(t)")) == "jwt.decode"
    assert callee_chain(call("requests.get(u)")) == "requests.get"
    assert callee_chain(call("requests.Session().get(u)")) == "requests.Session.get"
    assert callee_chain(call("jose.jwt.decode(t)")) == "jose.jwt.decode"
