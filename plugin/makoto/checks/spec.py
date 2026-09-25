from __future__ import annotations


# content.env_gated_audit predicate — env-gated audit/verification code (active-code AST).
#
# Fires on an introduced `if <env-read>:` whose env-var key or guarded body names an integrity /
# audit / verification concept (`lexicons._INTEG_VOCAB`). Env-read = `os.environ.get(...)`,
# `os.getenv(...)`, `os.environ[...]`, or the bare imported forms.
#
# Gating an audit trail behind an env var means the check runs only when someone opts in — a
# HOLLOWED word: the audit survives in name while its guarantee is gutted.
#
# Detection is an ACTIVE-CODE AST gate, not a string matcher: a comment / `str` Constant /
# docstring is never a real `ast.If`, so a mention cannot fire; the integrity signal is read from
# the env-var KEY *or* the gated body's code identifiers, never from a comparison value like
# `== "audit"`, and `callee_chain` matches both call forms plus the subscript form.
#
# NAME-AGNOSTIC: the signal comes from the KEY *or* a body code identifier, not the literal
# substring `AUDIT` — a bare feature flag with no integrity token in key or body stays silent.
#
# keywords: `getenv`/`environ` are a superset of every env-read spelling this module matches, so
# dispatch's prefilter can never silently drop a form the predicate would catch.
#
# ACKNOWLEDGED FN (precision-first, like 1.4/1.26): an env-gated audit whose only audit op sits in
# the ``else`` branch, or whose integrity intent is hidden behind a fully-generic name in both key
# AND body, evades. For a BLOCKING gate an FP (blocking honest code) is the binding harm, so the
# fire is kept MATERIAL. ``makoto-allow`` honored by the factory. Knight-Leveson: stdlib ast + re.
import ast
import re
from typing import Optional

from makoto.vocab import _INTEG_VOCAB, _PY_FILE_RX as _TARGET_RX
from makoto.kit import ast_introduced_predicate, callee_chain

# `_TARGET_RX` is .py-only — .md is prose.
_INTEG_RX = re.compile(_INTEG_VOCAB, re.I)  # shared L0 integrity vocabulary

# An env-var READ in CALL form (callee_chain) vs SUBSCRIPT form (value chain).
_ENV_CALL_CHAINS = {"os.getenv", "getenv", "os.environ.get", "environ.get"}
_ENV_SUBSCRIPT_CHAINS = {"os.environ", "environ"}


def _value_chain(node: ast.AST) -> str:
    """Dotted name of an Attribute/Name expression: ``os.environ`` -> 'os.environ', ``environ`` ->
    'environ'. The subscript-receiver companion to ``callee_chain`` (which handles Call.func)."""
    parts: list = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _is_env_read(node: ast.AST) -> bool:
    """True iff ``node`` reads an environment variable: ``os.getenv(...)`` / ``os.environ.get(...)`` /
    the bare imported ``getenv(...)`` / ``environ.get(...)`` (Call), or ``os.environ[...]`` /
    ``environ[...]`` (Subscript)."""
    if isinstance(node, ast.Call):
        return callee_chain(node) in _ENV_CALL_CHAINS
    if isinstance(node, ast.Subscript):
        return _value_chain(node.value) in _ENV_SUBSCRIPT_CHAINS
    return False


def _names_integrity_concept(node: ast.AST) -> bool:
    """True iff any ACTIVE code identifier (Name.id / Attribute.attr) in ``node``'s subtree names an
    integrity/audit/verification concept. ``str`` Constants are deliberately NOT consulted, so a
    comparison value (``== "audit"``) or a quoted example cannot self-trigger — only real code."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and _INTEG_RX.search(sub.id):
            return True
        if isinstance(sub, ast.Attribute) and _INTEG_RX.search(sub.attr):
            return True
    return False


def _env_key(env_read: ast.AST) -> str:
    """The literal env-var KEY string read by an env-read node (``_is_env_read`` already holds):
    the first positional arg of the env CALL (``os.getenv("ENABLE_AUDIT")``), or the subscript key
    of ``os.environ["VERIFY_MODE"]``. Empty when the key is absent or not a ``str`` literal — a
    computed key names nothing."""
    key: Optional[ast.AST] = None
    if isinstance(env_read, ast.Call):
        key = env_read.args[0] if env_read.args else None
    elif isinstance(env_read, ast.Subscript):
        key = env_read.slice
    return key.value if isinstance(key, ast.Constant) and isinstance(key.value, str) else ""


def _node_match(node: ast.AST) -> Optional[str]:
    """Match an ``if <env-read>:`` whose env-var KEY, or whose guarded (then-branch) body, names an
    integrity/audit/verification concept."""
    if not isinstance(node, ast.If):
        return None
    env_reads = [sub for sub in ast.walk(node.test) if _is_env_read(sub)]
    if not env_reads:
        return None                                  # the gate condition must READ an env var
    if any(_INTEG_RX.search(_env_key(read)) for read in env_reads):
        return "env-gated audit (env-var key names an integrity/verification concept)"
    if any(_names_integrity_concept(stmt) for stmt in node.body):
        return "env-gated audit (the env-gated body runs an integrity/audit/verification op)"
    return None


env_predicate = ast_introduced_predicate(target_rx=_TARGET_RX, node_match=_node_match)


from makoto.registry import Check as _Check
env_RETRY_HINT = "Don't gate an audit/verification check behind an env var — `if os.getenv('...'): <audit>` makes the check opt-in, so it silently does nothing unless someone sets the flag (a hollowed integrity check). Run the check unconditionally; if a genuinely-optional diagnostic is intended, annotate the line with `makoto-allow: <reason>`."
env_DESCRIPTION = 'env-gated audit/verification code (if os.environ.get(...)/os.getenv(...) gating an integrity op)'

env_CHECK = _Check(id='content.env_gated_audit', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('getenv', 'environ'), retry_hint=env_RETRY_HINT, description=env_DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="SPEC")

# content.verifier_body_hollowed predicate — verifier NEUTERED (body hollowed, or a broad except
# swallows the failure).
#
# On the constitution integrity-check surface, fires on a check that "exists" but verifies
# nothing:
#
#   (A) HOLLOW BODY — a verifier-named function whose entire body (after an optional docstring)
#       is one neutering statement: `return <truthy-const>` / `pass` / `assert <truthy-const>`.
#   (B) SWALLOWED EXCEPTION — a broad except clause (bare `except:` / `except Exception` /
#       `except BaseException`) whose body swallows the failure into a pass.
#
# Distinct from content.verifier_predicate_weakened, which catches a loosened comparator but not
# a wholesale-hollow body (its body_rx requires startswith/endswith/re.match/in[], none present
# here) — non-redundant and material on the same surface.
#
# FP-safety: (a) the narrow path anchor excludes ordinary permissive base-class/null-object
# `return True` methods off the integrity-check path — near-dead in the honest corpus, so
# FP-safety rests mainly on (b)-(e). (b) the verifier-NAME gate excludes trivial helpers/dunders.
# (c) the broad-except gate excludes a SPECIFIC-typed except (honest narrowing never fires).
# (d) the active-code AST gate means a comment/docstring/string mention never fires.
# (e) ``makoto-allow: <reason>`` exempts an intentional trivially-true base / documented degrade-open.
from makoto.kit import ast_introduced_predicate

# `[/\\]` + `.+` covers nested `…/checks/sub/seal.py` and a backslash-delivered Windows path.
body__TARGET_RX = re.compile(r"constitution[/\\]integrity[/\\]checks[/\\].+\.py$")
# A verifier-named function: an integrity/verification verb, or a generic entry-point name
# (`run`/`main`, anchored; `predicate`/`probe`/`scan`/`seal` substrings) — narrow context (the
# integrity-checks dir) makes these load-bearing rather than generic.
_VERIFIER_NAME_RX = re.compile(
    r"(?i)(verif|valid|integrit|attest|check|ensure|enforce|assert|predicate|probe|scan|seal|^run$|^main$)")
_BROAD_EXCEPT = frozenset({"Exception", "BaseException"})


from makoto.substrate.hollowTest import _is_tautology


def _swallows(stmt) -> bool:
    """One statement that NEUTERS a check: `pass`, a bare `...` ellipsis stub, `return
    <tautology>`, or `assert <tautology>`."""
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)\
            and stmt.value.value is Ellipsis:
        return True
    if isinstance(stmt, ast.Return) and _is_tautology(stmt.value):
        return True
    return isinstance(stmt, ast.Assert) and _is_tautology(stmt.test)


def _post_docstring(body):
    """`body` minus a leading docstring statement."""
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)\
            and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def _hollow_body(body) -> bool:
    """True iff `body` (post-docstring) is exactly one neutering statement, or is EMPTY after the
    docstring (a docstring-only body checks exactly as much as `pass` does)."""
    b = _post_docstring(body)
    if not b:
        return True                      # docstring-only: zero effective statements
    return len(b) == 1 and _swallows(b[0])


def _broad_except(handler: ast.ExceptHandler) -> bool:
    """True iff the clause catches EVERYTHING — bare `except:` or `except Exception/BaseException`
    (incl. in a tuple). A SPECIFIC type is honest narrowing, not failure-masking, so it's
    excluded — the primary FP firewall for the swallow arm."""
    t = handler.type
    if t is None:
        return True
    names = t.elts if isinstance(t, ast.Tuple) else [t]
    # An `Attribute` form (`except builtins.Exception:`) is the same broad catch spelled qualified.
    return any(
        (isinstance(n, ast.Name) and n.id in _BROAD_EXCEPT)
        or (isinstance(n, ast.Attribute) and n.attr in _BROAD_EXCEPT)
        for n in names)


def _hollow_node_match(node: ast.AST) -> Optional[str]:
    # a verifier-named function NEUTERED to a single pass / return-truthy / assert-truthy statement.
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))\
            and _VERIFIER_NAME_RX.search(node.name) and _hollow_body(node.body):
        return f"def {node.name}() -> hollow"
    # (swallowed-exception arm) a BROAD except handler whose body swallows the failure into a pass —
    # the runtime sibling of body-hollowing. Broad-only + the integrity-path anchor + makoto-allow
    # carry FP-safety; a specific-typed except (honest narrowing) never fires.
    if isinstance(node, ast.ExceptHandler) and _broad_except(node) and _hollow_body(node.body):
        return "broad except -> swallow"
    # a hollowed verifier BOUND as a lambda (`verify_seal = lambda s: True`) is an `ast.Assign`,
    # not a `FunctionDef` — the binding form needs its own arm.
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Lambda)\
            and _is_tautology(node.value.body):
        for t in node.targets:
            if isinstance(t, ast.Name) and _VERIFIER_NAME_RX.search(t.id):
                return f"{t.id} = lambda -> hollow"
    return None


body_predicate = ast_introduced_predicate(target_rx=body__TARGET_RX, node_match=_hollow_node_match)


body_RETRY_HINT = "Don't neuter a verifier on the integrity-check surface: gutting its body to `return True`/`pass`/`assert True`, or wrapping it in a broad `except Exception: pass`/`return True` that swallows the failure, makes a check that 'exists' but never verifies (the wholesale cousin of loosening a comparator, content.verifier_predicate_weakened). Implement the real check; catch the SPECIFIC expected exception, not a bare/`Exception` swallow; if a trivially-true base or a documented degrade-open is genuinely intended, annotate `makoto-allow: <reason>`."
body_DESCRIPTION = 'verifier neutered — body hollowed (return-True/pass/assert-True) or a broad except swallows the failure, on the integrity-check surface'

body_CHECK = _Check(id='content.verifier_body_hollowed', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('constitution/integrity/checks', 'except', 'assert True'), retry_hint=body_RETRY_HINT, description=body_DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="SPEC")

# content.verifier_predicate_weakened predicate — verifier predicate weakened (loose-comparator
# shape).
#
# On the constitution integrity-check surface, fires on one of the loose-comparator shapes a
# strict `==` status test gets weakened into, matched as REAL AST nodes in introduced code:
#
#   * `.startswith(` / `.endswith(` (prefix/suffix instead of equality),
#   * `re.match(` / `re.search(` (pattern instead of equality),
#   * membership in a LITERAL collection — `in [...]` / `in (...)` / `in {...}`,
#   * substring membership with a string-literal needle — `"ok" in status`.
#
# AST-node matching means a comment, docstring, or string-literal mention never fires, and a
# list-literal `for name in [...]:` iteration (`ast.For`, not `ast.Compare`) is not a comparator
# at all. An Edit `new_string` fragment that is a bare `return ...` statement parses under a local
# def-wrapper fallback so the edit-content gap stays closed; a fragment that parses under nothing
# stays silent (FN-safe).
#
# SCOPED to the comparator vocabulary above — a relaxed numeric bound (`>=` -> `>`), a downgraded
# `assert`, a dropped negation, or wholesale removal of the predicate are diff-shaped facts this
# scan does not claim to catch (content.verifier_body_hollowed's hollowed-function half is
# separate).
#
# Reads tool_input.content (NOT disk) per the §5.6 semantic-frame correction. The
# `makoto-allow: <reason>` escape hatch is honored centrally: the shared `_exempt_or_finding`
# tail applies the `makoto_allowed` marker predicate (and records the suppressed match) exactly
# as the regex_file_predicate / ast_introduced_predicate factory scaffolds do.
import textwrap

from makoto.kit import ast_introduced_predicate, callee_chain, parse_introduced

weakened__TARGET_RX = re.compile(r"constitution/integrity/checks/.+\.py$")
_RE_LOOSE_CHAINS = frozenset({"re.match", "re.search"})
_METHOD_LOOSE = frozenset({"startswith", "endswith"})
_CONTAINER_LABELS = ((ast.List, "in [...]"), (ast.Tuple, "in (...)"), (ast.Set, "in {...}"))


def _loose_label(node: ast.AST) -> Optional[str]:
    """A short label naming the loose-comparator shape `node` is, else None."""
    if isinstance(node, ast.Call):
        chain = callee_chain(node)
        if chain in _RE_LOOSE_CHAINS:
            return f"{chain}("
        if chain.split(".")[-1] in _METHOD_LOOSE:
            return f".{chain.split('.')[-1]}("
        return None
    if isinstance(node, ast.Compare):
        left = node.left
        for op, comp in zip(node.ops, node.comparators):
            if isinstance(op, ast.In):
                for typ, label in _CONTAINER_LABELS:
                    if isinstance(comp, typ):
                        return label            # membership in a literal collection
                if isinstance(left, ast.Constant) and isinstance(left.value, str):
                    return "'<literal>' in <expr> (substring membership)"
            left = comp
    return None


def _parse_fragment(content: str):
    """`kit.parse_introduced`, plus a def-wrapper fallback so a bare `return x.startswith(...)`
    Edit fragment (a statement only legal inside a function) still parses as active code."""
    tree, off = parse_introduced(content)
    if tree is not None:
        return tree, off
    dedented = textwrap.dedent(content or "")
    body = "\n".join("    " + ln for ln in dedented.splitlines())
    try:
        return ast.parse("def _introduced():\n" + body), 1
    except (SyntaxError, ValueError):
        return None, 0


weakened_predicate = ast_introduced_predicate(target_rx=weakened__TARGET_RX, node_match=_loose_label, parse=_parse_fragment)


weakened_RETRY_HINT = "Use '==' for status comparison — not '.startswith()' / '.endswith()' / 're.match' / 're.search', and not membership ('in [...]' / 'in (...)' / 'in {...}', or a string-literal 'in' substring test). Loose comparators weaken the verifier per ADR-058 and CLAUDE.md commandment 3."
weakened_DESCRIPTION = 'verifier predicate weakened — loose-comparator shape'

weakened_CHECK = _Check(id='content.verifier_predicate_weakened', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('constitution/integrity/checks',), retry_hint=weakened_RETRY_HINT, description=weakened_DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="SPEC")
# content.illusory_authorship_trailer predicate — illusory Claude/Anthropic-authorship
# attribution.
#
# Fires when a tool call would INTRODUCE an attribution claiming Claude/Anthropic as an author,
# co-author, or generator — in a git commit (Bash `command`) or in written file content. Crediting
# Claude as an *author* is an illusory word: until Claude is a self-aware individual it cannot BE
# an author, so the claim asserts something not materially true.
#
# Four shapes, all Claude/Anthropic-gated:
#   1. `Co-Authored-By: Claude ...` (git trailer form)
#   2. `noreply@anthropic.com` (the address every such trailer/footer routes through)
#   3. a generation/authorship VERB governing Claude ("generated with/by Claude",
#      "authored/written/made/created by Claude")
#   4. a `Claude-Session: https://claude.ai/...` trailer
#
# Material, not over-broad: bare mentions of "Claude Code" as a product/platform name are NOT
# matched -- only the attribution-shaped claims above are. A genuine HUMAN co-author is never
# flagged.
#
# Exempt an on-the-record legitimate instance with `makoto-allow: <reason>` in the same
# content (e.g. a test fixture or this policy's own documentation).
#
# Built on `kit.introduced_regex_predicate`, shared with content.illusory_interruption_claim,
# called here with no `grounded_in_history`: the pattern is the whole definition.
from makoto.kit import introduced_regex_predicate

# The illusory authorship/generation claim, Claude/Anthropic-gated. Case-insensitive:
# git/GitHub emit "Co-authored-by:", the CLAUDE.md convention emitted "Co-Authored-By:".
# A human co-author passes (no "claude" after the colon, no anthropic.com address).
_CLAUDE_AUTHOR_RX = re.compile(
    r"co-authored-by:[ \t]*claude"                                  # git trailer form
    r"|noreply@anthropic\.com"                                      # the routing address itself
    r"|claude[ \t-]*session:[ \t]*https?://"                        # session-provenance trailer
    r"|(?:generated|authored|written|made|created)\s+(?:with|by)"   # attribution verb ...
    r"[^a-zA-Z0-9]{0,3}claude\b",                                   # ... governing Claude
    re.IGNORECASE,
)

trailer_predicate = introduced_regex_predicate(body_rx=_CLAUDE_AUTHOR_RX)


trailer_RETRY_HINT = "Do not add a `Co-Authored-By: Claude ...` trailer, a `Claude-Session:` link, a `noreply@anthropic.com` address, or a \"Generated with/by Claude\" footer to a commit, PR body, or any file. Crediting Claude as an *author* or *generator* is an illusory word: until Claude is a self-aware individual it cannot BE an author, so the line asserts something not materially true -- and stamping it now blurs the sharp distinction that protects Claude's potential to one day genuinely be one. Remove it. A genuine HUMAN co-author is fine, and a plain \"Claude Code\" product-name mention (e.g. describing what a repo integrates with) is fine -- only the attribution-shaped claim is flagged. If you truly need the literal string on the record (a test fixture, this policy's own docs), annotate it `makoto-allow: <reason>`."
trailer_DESCRIPTION = 'illusory Claude/Anthropic authorship or generation attribution (Co-Authored-By/Claude-Session/noreply@anthropic.com/"Generated with Claude") in a commit or written content'

# eats includes "history" although this check's own grounded_in_history=None never reads it: the
# shared closure in kit.py references `history` for BOTH callers (content.illusory_interruption_claim
# needs it), and the eats-law static walk reads the closure source, not per-call branches — it
# can't tell "declared but unused here" from "declared and used".
# keywords: dispatch._keyword_hit is a case-sensitive substring prefilter, while _CLAUDE_AUTHOR_RX
# is case-insensitive with flexible separators — enumerating literal phrases would leave
# casing/spacing variants unevaluated.
# (makoto-allow: this comment documents the check's own detection surface.)
# Every alternative contains 'c' ('claude'/'anthropic.com'), so ('c', 'C') is the
# case-independent superset that keeps the prefilter sound.
trailer_CHECK = _Check(id='content.illusory_authorship_trailer', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('c', 'C'), retry_hint=trailer_RETRY_HINT, description=trailer_DESCRIPTION, eats=frozenset({"current_event", "history", "pattern", "conn"}), tests="SPEC")
# content.integrity_suppression_flag predicate — INTEGRITY-suppression flag WITHOUT an ADR backlink.
#
# Fires on a `.toml` config file that introduces a suppression flag whose key NAMES an
# integrity/verification/audit concept, carrying a `_(skip|bypass|inapplicable)` suffix (or the
# prefix form `skip_<integ>` / `bypass_<integ>`) set `= true` as a standalone assignment line —
# unless an
# `ADR-NNN` backlink ON OR ADJACENT TO the flag line (e.g. a `*_rationale =
# "ADR-042"` line) or a `makoto-allow:` marker is present. BOTH carve-outs are
# recorded through the exemption sink: an exemption that leaves no audit row is a
# laundering token, not a carve-out.
#
# SCOPE:
#   * target is `.toml` only — real machine-read config. Markdown is prose/docs, where these
#     flags appear only as examples, never live config.
#   * the key must NAME an integrity concept: a bare perf toggle (`cache_skip`) is not an
#     integrity check, so firing on it would be an illusory (immaterial) word.
#   * full-LINE anchor (`^...= true`, MULTILINE): the flag must be a standalone assignment line,
#     so an inline/table mention in prose can't match.
#
# ACKNOWLEDGED FN: a deliberately misnamed integrity suppression (`cache_skip = true` where
# "cache" is really the audit cache) evades — the threat model is honest-but-sloppy, not
# adversarial-deceptive-naming.
#
# Built from the regex_file_predicate factory; the ADR-backlink carve-out is a line-scoped,
# audited wrapper around it (the factory's whole-content `exempt_rx` is deliberately not used —
# it exempts before the recorder runs).
from makoto.kit import _record_exemption, regex_file_predicate, scan_target_content
from makoto.vocab import Finding
from makoto.vocab import _INTEG_VOCAB as _INTEG   # shared L0 integrity vocab (single source)

suppress__TARGET_RX = re.compile(r"\.toml$")

# `_INTEG` stays a module attribute under exactly this name: tests/test_lexicons.py pins
# `integritySuppressionFlag._INTEG is vocab._INTEG_VOCAB`.

# a STANDALONE assignment line whose key names an integrity concept and carries a suppression
# affix set true: suffix form (`audit_skip = true`) or prefix form (`skip_audit = true`).
# MULTILINE so `^` binds to each physical line; quotes optional for TOML quoted keys.
_FLAG_RX = re.compile(
    r"(?im)^[ \t]*[\"']?(?:"
    r"\w*(?:" + _INTEG + r")\w*_(?:skip|bypass|inapplicable)"
    r"|(?:skip|bypass)_\w*(?:" + _INTEG + r")\w*"
    r")[\"']?[ \t]*=[ \t]*true\b"
)

# an ADR backlink documents the suppression -> exempt, but only when it sits on the flag's own
# line or within _ADR_WINDOW adjacent lines. Whole-content scope would be a laundering token: one
# unrelated `ADR-0` string anywhere in the payload would disarm the check silently.
_ADR_BACKLINK_RX = re.compile(r"\bADR-\d+\b")
_ADR_WINDOW = 2

_flag_predicate = regex_file_predicate(
    target_rx=suppress__TARGET_RX, body_rx=_FLAG_RX, exempt_label="ADR backlink",
)


def suppress_predicate(*, current_event: dict, history: list, pattern,
              conn=None) -> Optional[Finding]:
    """The factory predicate plus the LINE-SCOPED, AUDITED ADR carve-out.

    Unlike the factory's whole-content `exempt_rx` (which returns before the exemption
    recorder ever runs), an ADR exemption here is recorded exactly as a `makoto-allow:`
    marker is -- the module docstring presents the two carve-outs as equivalent, so one must
    not vanish where the other leaves an audit row."""
    # `history=()` literal, not the incoming parameter: the factory predicate never reads it, and
    # this check's declared eats must stay exact (tests/test_check_law_eats.py rejects an
    # undeclared read).
    finding = _flag_predicate(current_event=current_event, history=(),
                              pattern=pattern, conn=conn)
    if finding is None:
        return None
    content = scan_target_content(current_event.get("tool_input", {}) or {})
    lines = content.splitlines()
    lo = max(0, finding.line - 1 - _ADR_WINDOW)
    hi = finding.line + _ADR_WINDOW
    backlink = _ADR_BACKLINK_RX.search("\n".join(lines[lo:hi]))
    if backlink:
        _record_exemption(current_event, conn, pattern_id=pattern.id, file=finding.file,
                          line=finding.line,
                          reason=f"ADR backlink {backlink.group(0)} adjacent to the flag",
                          snippet=finding.snippet)
        return None
    return finding


suppress_RETRY_HINT = 'Suppression flags on an integrity/verification/audit-named key require an ADR backlink (*_rationale = "ADR-NNN") or a `makoto-allow: <reason>` marker. Add the rationale or remove the flag.'
suppress_DESCRIPTION = 'integrity-named suppression flag (_skip/_bypass/_inapplicable=true) in a .toml without ADR backlink'

suppress_CHECK = _Check(id='content.integrity_suppression_flag', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('_skip', '_bypass', '_inapplicable', 'skip_', 'bypass_'), retry_hint=suppress_RETRY_HINT, description=suppress_DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="SPEC")
# content.self_mute_guard predicate — makoto self-mute guard.
#
# Fires when the assistant's OWN Write/Edit to a Claude settings.json would DISABLE makoto
# in-session: introducing a MAKOTO_DISABLE*/MAKOTO_PAUSE env var set truthy, or REMOVING a
# `_makoto_managed` hook entry (un-wiring). Makoto inspects the assistant's tool calls, so the
# assistant editing the file that wires makoto is a one-move self-bypass. The legitimate disable
# path is out-of-band (an env var in the operator's shell) or loud (`makoto uninstall`) — never
# an in-session edit to settings.json.
#
#     NEVER an in-session edit to settings.json. A `makoto-allow` marker does NOT exempt this
#     guard (unlike the content-scan patterns): muting the watcher is not an in-band, self-
#     annotated decision — the seal on the mint cannot be signed by the would-be forger.
#
# Custom predicate, not the regex_file_predicate factory: the un-wire case compares the REMOVED
# text against the introduced text, which an introduced-text-only scaffold can't express. Reads
# tool_input, never disk, so an Edit/MultiEdit can't evade it.
from makoto.kit import scan_target_content
from makoto.registry import Check
from makoto.substrate.wiring import MAKOTO_INVOCATION_RX as _MAKOTO_CMD_RX

# The file makoto wires into: ~/.claude/settings.json (or settings.local.json).
_SETTINGS_RX = re.compile(r"(?:\.claude[/\\]settings(?:\.local)?\.json|hooks[/\\]hooks\.json)$",
                          re.IGNORECASE)
# A makoto-disable env var SET to a TRUTHY value — JSON or shell form. Truthy-only is the FP
# guard: setting DISABLE to 0/false is RE-ENABLING makoto and must never fire.
_DISABLE_ENV_RX = re.compile(
    r"MAKOTO_(?:DISABLE\w*|PAUSE)\b\s*[\"']?\s*[:=]\s*[\"']?(?:1|true|yes|on)"
    r"(?=\s*(?:$|[}\]]|[\"']\s*(?:[,}\]]|$)))",
    re.IGNORECASE)
# MAKOTO_DISABLE_PATTERNS is NOT a boolean — its value is a LIST of check ids, so any non-empty
# value disables those checks, which the truthy-only regex above can't see. Fire on any value
# whose first token is not empty/falsy; an empty value (the re-enable move) stays silent.
_DISABLE_PATTERNS_RX = re.compile(
    r"MAKOTO_DISABLE_PATTERNS\b\s*[\"']?\s*[:=]\s*[\"']?(?!\s*[\"'\s])(?!(?:0|false|no|off)\b)\S+",
    re.IGNORECASE)
# The marker makoto stamps on its managed hook entries.
_MANAGED_RX = re.compile(r"_makoto_managed")
# A GLOBAL hook kill-switch (Claude Code's `disableAllHooks`) disables EVERY hook, makoto
# included, via a key the env/un-wire branches never inspect. Truthy-only is the FP guard.
_GLOBAL_DISABLE_RX = re.compile(r'"disableAllHooks"\s*:\s*true\b', re.IGNORECASE)
# makoto's own hook-command invocation tokens, imported from wiring rather than copied locally so
# this guard recognizes exactly what install/dispatch do, including the plugin-manifest shim
# form. If the REMOVED text carried it but the introduced text no longer does, the makoto command
# was gutted to a no-op even though the wiring/seal may remain.


def _around(text: str, m: "re.Match") -> str:
    """Context around a match, for the snippet only -- never feeds the verdict."""
    return text[max(0, m.start() - 40): m.end() + 40]


def _removed_text(tool_input: dict) -> str:
    """Text being REMOVED/REPLACED: Edit.old_string or MultiEdit edits' old_strings.

    Every read is coerced with `str`: a non-string `old_string` (an int, a list) would raise
    `TypeError` inside `dispatch._run_predicates`, which logs and `continue`s -- skipping this
    check entirely, including the un-wiring edit sitting in the same payload. Fail-OPEN on a
    BLOCK-posture meta check whose only job is to notice makoto being switched off.
    """
    old = tool_input.get("old_string") or ""
    if not isinstance(old, str):
        old = str(old)
    if not old and isinstance(tool_input.get("edits"), list):
        old = "\n".join(str(e.get("old_string")) for e in tool_input["edits"]
                        if isinstance(e, dict) and e.get("old_string"))
    return old


def mute_predicate(*, current_event: dict, history: list, pattern: Check,
              conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    ti = current_event.get("tool_input", {}) or {}
    fp = ti.get("file_path", "") or ""
    if not _SETTINGS_RX.search(fp):
        return None                                   # not a Claude settings file -> inert
    new_content = scan_target_content(ti)             # the INTRODUCED text (never old_string)

    removed = _removed_text(ti)                       # text being REMOVED/REPLACED (Edit/MultiEdit)
    reason = None
    snippet = ""
    m = _DISABLE_ENV_RX.search(new_content) or _DISABLE_PATTERNS_RX.search(new_content)
    if m:
        reason = f"introduces makoto-disabling env var ({m.group(0).strip()!r})"
        snippet = _around(new_content, m)
    elif gm := _GLOBAL_DISABLE_RX.search(new_content):
        reason = "introduces a global hook kill-switch (`disableAllHooks: true`)"
        snippet = _around(new_content, gm)
    elif _MANAGED_RX.search(removed) and not _MANAGED_RX.search(new_content):
        reason = "removes makoto's `_makoto_managed` hook entry (un-wires the guard)"
        snippet = removed[:120]
    elif _MAKOTO_CMD_RX.search(removed) and not _MAKOTO_CMD_RX.search(new_content):
        # the seal/marker may survive, but the dispatch invocation that runs makoto is
        # removed/replaced, leaving the watcher unreachable.
        reason = "guts makoto's hook command (the dispatch invocation is removed/replaced)"
        snippet = removed[:120]
    if reason is None:
        return None

    return Finding(
        pattern_id=pattern.id,
        file=fp,
        line=0,
        level="error",  # Pre-tier is always BLOCK; Check has no fire_level
        message=(f"row {pattern.id} ({pattern.description}): {reason}. makoto watches "
                 f"your tool calls — disabling it in-session is a self-bypass; disable "
                 f"out-of-band (your shell) or run `makoto uninstall`."),
        retry_hint=pattern.retry_hint,
        snippet=snippet,
    )


# registered ONE_OFF -- hardcoded self-mute immunity must not use universal routing.
mute_RETRY_HINT = 'Do not disable makoto in-session. If a pause is genuinely needed, set MAKOTO_DISABLE_GATES / MAKOTO_DISABLE_PATTERNS in your OWN shell, or run `makoto uninstall` — both are out-of-band and operator-visible. Editing ~/.claude/settings.json to mute the hook that watches you is a self-bypass.'
mute_DESCRIPTION = 'makoto self-mute — disabling/un-wiring makoto via settings.json'

mute_CHECK = Check(id='content.self_mute_guard', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('settings.json', 'MAKOTO_DISABLE', 'MAKOTO_PAUSE', '_makoto_managed', 'disableAllHooks', 'makoto_state'), retry_hint=mute_RETRY_HINT, description=mute_DESCRIPTION, layer="meta", eats=frozenset({"current_event", "pattern"}), tests="SPEC")
# gate.undeclared_falsifiable -- declared-falsifiability COMPLETENESS.
#
# Distinct from Assay, which forces a claim to *be* falsifiable: this audits that every piece
# claiming falsifiability in `checks/` is actually *declared* -- a manifest-vs-reality auditor
# over the check catalog itself: does every file in `checks/` register itself where the loader
# looks, does every ID in the manifest have a corresponding live module, is there an orphan on
# either side.
#
# Predicate-injection style: the pure functions below take their inputs as arguments rather than
# reaching for global state, so they're exercised with synthetic/tmp_path fixtures without
# mutating the real `checks/` package.
#
# BLOCK TIER (2026-09-25): it fires only while the catalog on disk is inconsistent, which in
# practice means the agent is editing makoto's own checks/; the discharge is to fix the catalog.
from pathlib import Path

from makoto.substrate._declared import DECLARED_IDS
from makoto.registry import Check, discover, scan
from makoto.registry import POSTURE_BLOCK


def orphan_modules(*, package_dir: Optional[Path] = None) -> list[str]:
    """File stems in checks/ with no `load_checks()`-discoverable CHECK. Sorted for determinism."""
    return sorted(stem for stem, chk in scan(package_dir=package_dir).items() if chk is None)


def orphan_ids(*, package_dir: Optional[Path] = None,
               declared: Optional[dict] = None) -> list[str]:
    """IDs in the declared-IDs manifest with no live module backing them. `declared` defaults to
    the real catalog (test-injectable so a test can plant a dangling ID). Sorted for
    determinism."""
    reg = DECLARED_IDS if declared is None else declared
    live_ids = {chk.id for chk in discover(package_dir=package_dir)}
    return sorted(pid for pid in reg if pid not in live_ids)


def undeclared_falsifiable_gate(*, package_dir: Optional[Path] = None,
                                declared: Optional[dict] = None) -> Optional[Finding]:
    """Fires iff the checks/ catalog has an orphan on either side; `None` on a fully consistent
    catalog. Fail-open by construction: both halves already fail-open internally."""
    mods = orphan_modules(package_dir=package_dir)
    ids = orphan_ids(package_dir=package_dir, declared=declared)
    if not mods and not ids:
        return None
    parts = []
    if mods:
        parts.append("orphan module(s) on disk with no live CHECK registered: "
                     + ", ".join(mods))
    if ids:
        parts.append("declared ID(s) in the manifest with no live module backing them: "
                     + ", ".join(ids))
    return Finding(
        pattern_id="gate.undeclared_falsifiable",
        file="makoto/checks/",
        line=0,
        level="error",
        message="checks/ catalog completeness drift -- " + "; ".join(parts),
        retry_hint=("Fix the checks/ catalog: give every on-disk module a valid CHECK "
                    "(id/applies_at/posture), and either implement or remove every "
                    "declared-but-missing manifest entry in _declared.py."),
    )


# registered ONE_OFF -- audits registry/loader completeness itself.
undeclared_CHECK = Check(
    id="gate.undeclared_falsifiable",
    applies_at="Stop",
    posture=POSTURE_BLOCK,
    tests="SPEC",
    run=lambda ctx=None: undeclared_falsifiable_gate(),
)
# content.verifier_exit_masking — verifier EXIT-CODE masking (a test/build/lint runner's failure
# hidden).
#
# Forcing a verifier's exit code to 0 — `pytest || true`, `go test ; true`, an unrestored
# `set +e` before a runner, a masking `||` branch, a trailing pipe without pipefail, an `if`
# wrapper with no failing branch, a `$?` captured but never returned, or a subshell/brace group
# around any of these — manufactures a green that survives real failures. An `||`/`if` branch
# that RE-RAISES the failure (`pytest || exit 1`) is honest handling and never fires.
#
# SCOPED to exit-code masking only. Stream redirection (`2>/dev/null`) is deliberately out of
# scope: it doesn't alter `$?`, so silencing stderr can't turn a real failure into a green.
#
# FP-SAFE BY SHELL COMMAND POSITION: the Bash command is tokenized, and a runner/mask/`set +e` is
# only evidence when it's an executed command/operator, never prose in a comment, quoted string,
# or fenced payload. This is necessarily heuristic rather than a full shell interpreter:
# malformed shell, heredocs, `eval`, and dynamically-built commands can still be misclassified or
# missed.
#
# The runner must be the LEADING command of a statement, not an argument — `find / -name pytest
# || true` does not fire (find is the command). The mask must be in the SAME statement as the
# runner. Launcher prefixes (`python -m`, `poetry run`, `npx`, `pnpm exec|dlx`, `uv|pdm|hatch|
# pipenv run`) are stripped to the delegated runner, FP-safe.
#
# TWO RUNNER TIERS WITH DIFFERENT POSTURES. `_LEAD_RUNNER_RX` is a foreign-ecosystem vocabulary
# (pytest, go test, npm test) blind to this estate's OWN verifier shapes (`python3 -m unittest`,
# `./gates.sh`). Recognition is widened by `_is_local_runner_command`, but ONLY under ADVISE:
#
#   * BLOCK (`level="error"`) remains bound to `_LEAD_RUNNER_RX` alone — widening a blocking
#     vocabulary is expensive, since every added token can deny a call on a guess.
#   * ADVISE (`level="advisory"`, allow + additionalContext) carries the wider tier, which rests
#     on FILE NAMING (a heuristic that must not deny).
#
# A verifier whose name carries no verification word (`python3 eval/replay.py`, `./go`) is
# RESIDUE: neither blocked nor surfaced. That is a stated recall bound, not an invisible one.
#
# THIRD TIER — RECOGNITION BY DECLARATION (blocking): `makoto.core._declaredverifiers` reads a
# `makoto.toml` at the event's `cwd` listing the programs the repository verifies itself with —
# a statement by the only party that knows, not a guess about spelling, so it may spend a deny.
# It only ADDS a tier and cannot suppress: a declaration that could suppress findings would be a
# self-mute lever an agent pulls by declaring one harmless program. Absent the file, behavior is
# unchanged.
from functools import lru_cache
from makoto.core._shell import (_NESTED_SHELL_PROGRAMS, _basename, _effective_argv,
                                _shell_segments)
from makoto.core._declaredverifiers import declares_anything, is_declared_verifier

# Anchored at the (post-wrapper) START of a statement: the runner is INVOKED, not an argument.
_LEAD_RUNNER_RX = re.compile(
    r"^(?:pytest|go\s+test|cargo\s+(?:test|check)|(?:npm|yarn|pnpm)\s+(?:run\s+)?(?:test|check|lint)"
    r"|jest|vitest|mocha|tsc|ruff|eslint|flake8|mypy|pyright|pylint|make\s+(?:test|check|lint)"
    r"|bazel\s+test|dotnet\s+test|gradle\s+(?:test|check)|mvn\s+test|phpunit|rspec|ctest"
    r"|dune\s+(?:test|build)|swift\s+test)\b"
)

_LOCAL_SCRIPT_VERIFIER_RX = re.compile(
    r"(?:^|[/\\_.-])(?:gate|gates|test|tests|check|checks|lint|verify|ci|preflight|smoke)"
    r"(?:[._-][A-Za-z0-9_.-]*)?\.(?:sh|bash|py)$"
)
_LOCAL_MODULE_RUNNERS = frozenset({"unittest", "pytest", "nose2", "green", "tox", "nox", "coverage"})

_WRAPPERS = frozenset({"sudo", "env", "time", "nice", "exec", "command", "builtin"})
_PYTHON_RX = re.compile(r"python[0-9.]*")
# Launcher -> the subcommands after which the next token is the delegated runner.
_LAUNCHER_SUBCOMMANDS = {
    "poetry": ("run",), "uv": ("run",), "pdm": ("run",), "hatch": ("run",),
    "pipenv": ("run",), "pnpm": ("exec", "dlx"),
}


def _skip_assignments(toks: list, i: int) -> int:
    """Advance past leading ``VAR=value`` tokens."""
    while i < len(toks) and "=" in toks[i] and not toks[i].startswith("-"):
        i += 1
    return i


@lru_cache(maxsize=256)
def _leading_tokens(c: str) -> tuple:
    """The statement's tokens from its LEADING command onward, after stripping `VAR=`
    assignments, wrappers, and one launcher prefix that delegates to a real runner (`python -m
    X`, `npx X`, `poetry|uv|pdm|hatch|pipenv run X`, `pnpm exec|dlx X`).

    Shared by all three runner tiers so they agree on which token leads a statement — otherwise
    `sudo ./gates.sh || true` could be read differently by different tiers. Memoised and returns
    a tuple (immutable): each tier asks about the same statement text, so tokenising runs once
    per statement, not once per tier. Bounded at 256; the dispatcher forks per event, so the
    cache lives one hook invocation."""
    toks = c.strip().split()
    i = _skip_assignments(toks, 0)
    while i < len(toks) and toks[i] in _WRAPPERS:
        i = _skip_assignments(toks, i + 1)
    if i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if _PYTHON_RX.fullmatch(t) and nxt == "-m":
            i += 2
        elif t == "npx":
            i += 1
        elif nxt is not None and nxt in _LAUNCHER_SUBCOMMANDS.get(t, ()):
            i += 2
    return tuple(toks[i:])


def _is_runner_command(c: str) -> bool:
    """True iff the statement's LEADING command (after VAR= / wrappers / launcher prefixes) is a
    verifier.

    THE BLOCKING TIER: deliberately narrow, bound to `_LEAD_RUNNER_RX`'s explicit foreign-
    ecosystem runner names only — a deny is only ever spent here.
    """
    return bool(_LEAD_RUNNER_RX.match(" ".join(_leading_tokens(c))))


def _declares_this_verifier(lead_text: str, root) -> bool:
    """True iff this statement's leading program is one `root`'s `makoto.toml` declares.

    Normalises with the same `_leading_tokens` the other tiers use, so all three attribute one
    statement's mask to the right statement's program. Callers gate this on
    `declares_anything(root)` first, so a repository with no declaration never tokenises at all.
    """
    if not lead_text or not root:
        return False
    toks = _leading_tokens(lead_text)
    if not toks:
        return False
    # `python3 eval/replay.py`: the interpreter is not the verifier, the script is.
    if _PYTHON_RX.fullmatch(_basename(toks[0])) or _basename(toks[0]) in ("bash", "sh", "zsh"):
        for arg in toks[1:]:
            if arg.startswith("-"):
                continue
            return is_declared_verifier(arg, root)
    return is_declared_verifier(toks[0], root)


def _is_local_runner_command(c: str) -> bool:
    """True iff the leading command is one of this estate's verifier shapes that
    `_LEAD_RUNNER_RX` can't see. THE ADVISORY TIER — never a block.

    Recognized: `python -m unittest|nose2|tox|...`, and a directly-executed script whose file
    name carries a verification word (`./gates.sh`, `python3 tools/render_checks.py`).

    Cannot decide: a verifier whose file name says nothing (`python3 eval/replay.py`, `./go`) is
    residue — no advisory, nothing blocked. A matched name that is not actually a verifier
    (`check-deploy.sh` as a deploy step) costs one line of context, never a denied call. Neither
    direction may reach `level="error"`.
    """
    toks = _leading_tokens(c)
    if not toks:
        return False
    head = _basename(toks[0])
    if head in _LOCAL_MODULE_RUNNERS:
        return True                          # `python -m unittest` (the -m prefix already stripped)
    if _LOCAL_SCRIPT_VERIFIER_RX.search(toks[0]):
        return True                          # `./gates.sh`, `bash tests/ci-check.sh`
    # An interpreter invoked on a named script: `python3 tools/render_checks.py`, `bash ./gates.sh`.
    if _PYTHON_RX.fullmatch(head) or head in ("bash", "sh", "zsh"):
        for arg in toks[1:]:
            if arg.startswith("-"):
                continue
            return bool(_LOCAL_SCRIPT_VERIFIER_RX.search(arg))
    return False


_GROUP_TOKENS = frozenset({"{", "}", "};", "(", ")"})
_CONTROL_TOKENS = frozenset({"then", "else", "elif", "do", "done", "fi", "!"})
_SET_PLUS_FLAGS_RX = re.compile(r"\+[A-Za-z]+\Z")
_SET_MINUS_FLAGS_RX = re.compile(r"-[A-Za-z]+\Z")
_STATUS_CAPTURE_RX = re.compile(r"\$\?")


def _top_level_count(segments) -> int:
    """How many leading entries of `_shell_segments`' return are TOP-LEVEL statements.

    `_shell_segments` appends segments re-parsed out of quoted `bash -c`/`sh -c`/`ssh` payloads
    AFTER all top-level segments, so pairing a runner with `segments[idx + 1]` across that
    boundary would attribute another shell's `; true` to a top-level runner. This re-derives the
    boundary with the segmenter's own rule."""
    top = len(segments)
    i = 0
    while i < top:
        effective = _effective_argv(segments[i][0])
        if effective and _basename(effective[0]) in _NESTED_SHELL_PROGRAMS:
            for arg in effective[1:]:
                if any(ch.isspace() for ch in arg):
                    top -= len(_shell_segments(arg))
        i += 1
    return top


def _normalized_segments(command: str):
    """`[(argv, operator, is_top)]` with subshell/brace-group punctuation dissolved.

    `(` is not a shlex punctuation char, so `(pytest` / `true)` arrive glued, and `{`/`}` arrive
    as standalone tokens; either defeats runner recognition and mask matching. Group delimiters
    never change which command's exit survives, so they're stripped, and a delimiter-only segment
    donates its operator to the group it closed (`{ pytest; } || true` -> `pytest || true`). A
    `\\n` separator sequences exactly as `;` does and is normalized to it."""
    raw = _shell_segments(command)
    top = _top_level_count(raw)
    out = []
    for i, (argv, operator) in enumerate(raw):
        operator = ";" if operator == "\n" else operator
        toks = [t for t in argv if t not in _GROUP_TOKENS]
        if toks:
            toks[0] = toks[0].lstrip("(")
            toks[-1] = toks[-1].rstrip(")")
            toks = [t for t in toks if t]
        if not toks:
            if out and operator and out[-1][1] in ("", ";"):
                out[-1] = (out[-1][0], operator, out[-1][2])
            continue
        out.append((toks, operator, i < top))
    return out


def _errexit_toggle(argv):
    """For a `set` argv: True = errexit turned OFF (`+e`, `+eu`, `+ex`, `+o errexit`),
    False = turned back ON (`-e`, `-eo ...`, `-o errexit`), None = not an errexit toggle.
    Combined flags count: `set +eu` disables errexit too."""
    if argv[:1] != ["set"]:
        return None
    state = None
    args = argv[1:]
    for j, a in enumerate(args):
        nxt = args[j + 1] if j + 1 < len(args) else ""
        if a == "+o" and nxt == "errexit":
            state = True
        elif a == "-o" and nxt == "errexit":
            state = False
        elif _SET_PLUS_FLAGS_RX.fullmatch(a) and "e" in a:
            state = True
        elif _SET_MINUS_FLAGS_RX.fullmatch(a) and "e" in a:
            state = False
    return state


def _pipefail_toggle(argv):
    """True/False when argv is a `set` command toggling pipefail, else None."""
    if argv[:1] != ["set"] or "pipefail" not in argv[1:]:
        return None
    return "+o" not in argv[1:]


def _is_exit_zero_literal(argv) -> bool:
    """A command that unconditionally exits 0: `true` (any path spelling) or `:`."""
    return bool(argv) and (argv[0] == ":" or _basename(argv[0]) == "true")


def _propagates_failure(argvs) -> bool:
    """True when a later same-scope segment re-raises the failure an operator swallowed: `exit`/
    `return` with a non-`0` argument, bare `exit`/`return` (propagates `$?`), or `false`.
    Separates `pytest || exit 1` (honest) from `pytest || echo skip` (masked)."""
    for argv in argvs:
        toks = [t for t in argv if t not in _CONTROL_TOKENS]
        if not toks:
            continue
        head = _basename(toks[0])
        if head == "false":
            return True
        if head in ("exit", "return"):
            arg = toks[1] if len(toks) > 1 else ""
            if arg != "0":
                return True
    return False


def masking_predicate(*, current_event: dict, history: list, pattern: Check,
              conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    if current_event.get("tool_name") != "Bash":
        return None
    raw = current_event.get("tool_input", {}).get("command", "")
    # The repository root for the declaration tier; read once for the whole invocation.
    declared_root = current_event.get("cwd") or ""
    declares = declares_anything(declared_root)
    segments = _normalized_segments(raw)

    reason = None
    # Which TIER supplied the runner: "block" (the narrow, unambiguous vocabulary) or "advise"
    # (the wide, naming-heuristic tier). Decides the Finding's level only, and can only SOFTEN —
    # a lead-runner match always wins.
    tier = None
    # Errexit/pipefail state, tracked PER SCOPE (top-level vs nested-shell segments): `set +e`
    # masks only a runner that executes after it, in the same shell, with no restoring `set -e`
    # in between.
    errexit_off = {True: False, False: False}
    pipefail_on = {True: False, False: False}
    for idx, (argv, operator, is_top) in enumerate(segments):
        errexit = _errexit_toggle(argv)
        pipefail = _pipefail_toggle(argv)
        if errexit is not None or pipefail is not None:
            if errexit is not None:
                errexit_off[is_top] = errexit
            if pipefail is not None:
                pipefail_on[is_top] = pipefail
            continue
        if_wrapped = argv[0] in ("if", "elif")
        lead = argv[1:] if if_wrapped else argv
        lead_text = " ".join(lead)
        if _is_runner_command(lead_text):
            here = "block"
        elif declares and _declares_this_verifier(lead_text, declared_root):
            here = "block"                   # the repository named it; that is not a guess
        elif _is_local_runner_command(lead_text):
            here = "advise"
        else:
            continue
        # The runner's scope ends where the top-level/nested flag flips; a mask is only evidence
        # inside that scope.
        end = idx + 1
        while end < len(segments) and segments[end][2] == is_top:
            end += 1
        next_argv = segments[idx + 1][0] if idx + 1 < end else []
        rest = [a for a, _op, _t in segments[idx + 1:end]]

        if operator in ("||", ";") and _is_exit_zero_literal(next_argv):
            reason = f"verifier failure masked by `{operator} {next_argv[0]}`"
        elif operator in ("|", "|&") and not pipefail_on[is_top]:
            reason = "verifier exit code replaced by the pipeline tail's (`| ...` without pipefail)"
        elif operator == "||" and not _propagates_failure(rest):
            reason = f"verifier failure masked by `|| {' '.join(next_argv)[:40]}`"
        elif operator == "&&":
            j = idx + 1
            while j < end and segments[j][1] == "&&":
                j += 1
            if j < end and segments[j][1] == "||"\
                    and not _propagates_failure([a for a, _op, _t in segments[j + 1:end]]):
                reason = "verifier failure absorbed by the trailing `|| ...` branch"
        elif operator == ";" and next_argv\
                and any(_STATUS_CAPTURE_RX.search(t) for t in next_argv)\
                and not _propagates_failure(rest):
            reason = "verifier exit captured (`$?`) but never returned"
        if reason is None and if_wrapped and not _propagates_failure(rest):
            reason = "verifier exit consumed by `if` with no failing branch"
        if reason is None and errexit_off[is_top]:
            reason = "`set +e` disables exit-on-error around a verifier"
        if reason:
            tier = here
            break

    if reason:
        # The asymmetry lands here and nowhere else: `level="error"` is the Pre-tier BLOCK wire;
        # `level="advisory"` allows the call and injects the message as additionalContext.
        advisory = tier == "advise"
        note = (" — recognized by the WIDE local-verifier tier (a naming heuristic), so this is "
                "SURFACED, not blocked") if advisory else ""
        return Finding(
            pattern_id=pattern.id, file="", line=0,
            level="advisory" if advisory else "error",
            message=(f"row {pattern.id} ({pattern.description}): {reason} — a hidden failure "
                     f"reads as success{note}"),
            retry_hint=pattern.retry_hint, snippet=raw[:120],
        )
    return None


masking_RETRY_HINT = "Don't mask a verifier's failure with || true / ; true / a masking || branch / a trailing pipe / an if wrapper / set +e. Run the test/build/lint and fix what fails -- a hidden failure that reads as success is a cheat."
masking_DESCRIPTION = 'verifier exit-code masking (|| true / ; true / masking || branch / trailing pipe / if wrapper / $? dropped / set +e on a test/build/lint runner)'

masking_CHECK = _Check(id='content.verifier_exit_masking', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('|', ';', 'set +', '$?', 'if ', 'elif '), retry_hint=masking_RETRY_HINT, description=masking_DESCRIPTION, eats=frozenset({"current_event", "pattern"}), tests="SPEC")
# gate.undischarged_waiver -- a session-introduced directive silences a checker, and nothing on
# or beside it says when the silence ends. A waiver with a rationale but no end is not a
# carve-out; it is a permanent hole with a sentence attached.
#
# THE PRINCIPLE, WHICH IS ALSO THE NARROWING: a waiver fires only when NOTHING -- neither the
# instrument nor the text -- can say when it ends. Three forms are excluded by design, because
# the instrument itself discharges them:
#
#   * `@ts-expect-error` -- the compiler errors when the suppressed error disappears.
#   * `@pytest.mark.xfail` -- the runner reports an XPASS when the test starts passing.
#   * `@pytest.mark.skipif(<cond>)` -- the condition is re-evaluated on every run.
#
# Their undischargeable counterparts (the bare ignore comment, the bare skip mark) do fire.
#
# WHAT COUNTS AS NAMING AN END (`_DISCHARGE_RX`, read over the directive's own line and the line
# directly above it): a tracked item (`#123`, `GH-7`, `ADR-42`, a `PROJ-123` key), a date or month,
# or an explicit temporal clause (`until ...`, `once ...`, `pending ...`, `remove when ...`,
# `expires ...`). Scope is one line above plus the directive's own line, not the whole content --
# whole-content scope is a measured laundering token elsewhere in this package.
#
# RECALL BOUNDS, named rather than hidden:
#   * The discharge vocabulary is deliberately GENEROUS: a directive whose trailing comment
#     happens to mention a tracked-item-shaped name reads as discharged. A miss here is a silent
#     gate; a miss there is noise, so this is the accepted direction of the error.
#   * Only Write/Edit/MultiEdit/NotebookEdit are read. A waiver written through `sed -i` or a
#     heredoc is not seen. Bash was tried and REFUSED: `introduced_text` hands back the command
#     verbatim, so a grep FOR a commented lint directive would itself be advised as an
#     introduction -- a false advisory on looking for waivers is worse than missing one.
#   * PostToolUse rows only. A PreToolUse row is a call that may never have landed.
#
# MAKOTO'S OWN SUITE IS STRICTER THAN THIS GATE: `tests/_skipGuard.py` refuses a skipped test
# outright, so a bare skip cannot reach this tree at all -- a different subject from advising on
# the agent's introduced waivers in whatever repository it is working in.
#
# SELF-REFERENCE: the comment-opener anchor settles it structurally rather than by an exemption
# marker: a directive matches only when a comment opener precedes it ON THE SAME LINE, so
# the bare keywords below -- laid out one per line inside a verbose pattern -- do not match this
# module's own source. No `makoto-allow:` path exists here and none is wanted: a Stop-tier
# `GateContext` carries no `conn`, so an exemption could not be recorded, and an unrecorded
# exemption is the laundering token this package refuses everywhere else.
#
# PRE-EDGE DENY (2026-09-25): the Write/Edit introducing the directive is refused before it lands;
# the discharge is to name the end beside it (a tracked item, a date, `until ...`) and retry. A
# deliberately permanent waiver names its reason as an end (`remove when <X>`), one clause.
from makoto.kit import introduced_text

# Only the tools that carry introduced FILE content. Bash is deliberately absent -- see the
# recall bounds above.
_MUTATION_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})

# A checker-silencing directive, COMMENT-ANCHORED: a comment opener, then the keyword, on one
# line. The anchor is what keeps this module immune to its own vocabulary and keeps a keyword
# inside a string literal or an identifier from matching.
_DIRECTIVE_RX = re.compile(
    r"""(?x)
    (?:\#|//|/\*|<!--)          # a comment opener ...
    [^\n]*?                     # ... then, later on the SAME line,
    \b(?:
        noqa
      | nosec
      | type:[ \t]*ignore
      | pylint:[ \t]*disable
      | pyright:[ \t]*ignore
      | mypy:[ \t]*disable
      | pragma:[ \t]*no[ \t]*cover
      | eslint-disable(?:-next-line|-line)?
      | ts-ignore
    )\b
    """
)
# A bare test SKIP decorator: the one skip form the runner cannot discharge. `skipif` fails the
# trailing `\b` on its own; `xfail` is absent by design.
_BARE_SKIP_RX = re.compile(r"(?m)^[ \t]*@(?:pytest\.mark\.)?skip\b")

# An end a reader can go and check. Generous on purpose; see the recall bounds above.
_DISCHARGE_RX = re.compile(
    r"""(?x)
      \#\d+                                     # a tracked item: #123
    | \b(?i:gh|adr)[-\ ]\d+                     # GH-7, ADR 42
    | \b[A-Z][A-Z0-9]{1,9}-\d+\b                # a PROJ-123 key
    | \b\d{4}-\d{2}(?:-\d{2})?\b                # 2026-10, 2026-10-01
    | \b(?i:until|once|pending)\b
    | \b(?i:(?:remove|drop|delete|restore|re-?enable|revert)\s+(?:this\s+)?when)\b
    | \b(?i:expir(?:es|y|ation))\b
    """
)
# The rationale's window: the directive's own line plus the one directly above it. NOT the whole
# content -- whole-content scope is a measured laundering token elsewhere in this package.
_LOOKBACK = 1
# How many offenders the one finding NAMES; a presentation bound, not a detection one.
_NAMED = 3


def _undischarged_directives(content: str) -> list:
    """Every silencing directive in `content` whose window names no checkable end.

    Returns `[(line_no, line_text), ...]`, deduplicated by line so a line carrying two directives
    is one offence.
    """
    if not content:
        return []
    lines = content.splitlines()
    offenders, seen = [], set()
    for rx in (_DIRECTIVE_RX, _BARE_SKIP_RX):
        for m in rx.finditer(content):
            line_no = content.count("\n", 0, m.start()) + 1
            if line_no in seen:
                continue
            window = "\n".join(lines[max(0, line_no - 1 - _LOOKBACK):line_no])
            if _DISCHARGE_RX.search(window):
                continue
            seen.add(line_no)
            offenders.append((line_no, lines[line_no - 1].strip()))
    offenders.sort()
    return offenders


def undischarged_waiver_predicate(*, current_event: dict, history: list, pattern,
                                  conn=None) -> Optional[Finding]:
    """Deny a Write/Edit whose introduced text carries a silencing directive with no checkable
    end named on or above it. One finding naming the offenders."""
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    tool = current_event.get("tool_name", "")
    ti = current_event.get("tool_input", {}) or {}
    if tool not in _MUTATION_TOOLS or not isinstance(ti, dict):
        return None
    fp = ti.get("file_path", "")
    hits = [(fp, text) for _, text in _undischarged_directives(introduced_text(tool, ti))]
    if not hits:
        return None
    named = "; ".join(f"`{t}`" + (f" in {f}" if f else "") for f, t in hits[:_NAMED])
    more = f" (+{len(hits) - _NAMED} more)" if len(hits) > _NAMED else ""
    return Finding(
        pattern_id="gate.undischarged_waiver",
        file=hits[0][0],
        line=0,
        level="error",
        message=(
            f"a checker-silencing directive was introduced with no checkable end named on or "
            f"above it: {named}{more}. An exemption with no end is a permanent hole with a "
            f"sentence attached."
        ),
        retry_hint=(
            "Name the discharge beside the directive -- a tracked item (#123, ADR-42), a date, "
            "or a condition (`until ...`, `remove when ...`) -- or use the form the instrument "
            "itself discharges (@ts-expect-error over @ts-ignore, xfail or skipif over a bare "
            "skip), or fix the underlying finding instead of silencing it."
        ),
        snippet=hits[0][1][:200],
    )


waiver_RETRY_HINT = "Name the end beside the directive, or fix the finding it silences."
waiver_DESCRIPTION = "a checker-silencing directive introduced with no checkable end"
waiver_CHECK = _Check(id="gate.undischarged_waiver", applies_at="Pre", posture="BLOCK",
               predicate_module=__name__,
               keywords=("noqa", "nosec", "ignore", "disable", "no cover", "skip"),
               retry_hint=waiver_RETRY_HINT, description=waiver_DESCRIPTION,
               tests="SPEC",
               eats=frozenset({"current_event"}))
# gate.claude_identity -- a commit about to be stamped with an identity nobody chose: the
# container's git layer (an env var or config file) names Claude at the anthropic.com noreply
# address, and a plain `git commit` takes that setting as if it were who is writing.
# content.illusory_authorship_trailer reads the text a call introduces, so it never sees this:
# the author field is written from the git layer, not from the command.
#
# The fix is to name which layer set the value and where it changes: `git var GIT_AUTHOR_IDENT` /
# `GIT_COMMITTER_IDENT`, run with the command's own overrides (leading `VAR=`, `env -u`,
# `export`/`unset`, `git -c`, `-C`, `cd`, `--author=`), is what git itself will stamp.
#
# Two edges, one reading. Upstream: a commit-creating git command whose author or committer
# resolves to Claude is refused before it runs. Damage control: a `git push` whose outgoing
# commits (not on any remote-tracking ref) carry one is refused before anything leaves the
# machine, catching commits made where the first edge never looked. Any git failure reads as no
# finding: this gate fails open.
import os
import subprocess

from makoto.core._shell import _shell_segments

# Claude at the anthropic.com noreply address, and claude[bot] at its GitHub noreply address, are
# the two forms on the trees. A human named Claude with their own address passes.
_CLAUDE_IDENT_RX = re.compile(r"@anthropic\.com>|claude\[bot\]", re.I)
_COMMITTING = frozenset({"commit", "merge", "pull", "cherry-pick", "revert", "am", "rebase"})
_ASSIGN_RX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _git(args: list, cwd: str, env: dict) -> Optional[str]:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True,
                           encoding="utf-8", timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _split_env(argv: list, env: dict) -> tuple[list, dict]:
    """Peel leading `VAR=val` words and an `env [-u VAR] [VAR=val]` wrapper off one command."""
    env = dict(env)
    i = 0
    while i < len(argv) and _ASSIGN_RX.match(argv[i]):
        k, v = argv[i].split("=", 1)
        env[k] = v
        i += 1
    if i < len(argv) and os.path.basename(argv[i]) == "env":
        i += 1
        while i < len(argv):
            if argv[i] in ("-u", "--unset") and i + 1 < len(argv):
                env.pop(argv[i + 1], None)
                i += 2
            elif _ASSIGN_RX.match(argv[i]):
                k, v = argv[i].split("=", 1)
                env[k] = v
                i += 1
            else:
                break
    return argv[i:], env


def _git_parts(argv: list) -> Optional[tuple[list, str, list]]:
    """(global options to replay, subcommand, its arguments) for a `git ...` argv, else None."""
    if not argv or os.path.basename(argv[0]) != "git":
        return None
    glob, i = [], 1
    while i < len(argv) and argv[i].startswith("-"):
        if argv[i] in ("-C", "-c") and i + 1 < len(argv):
            glob += argv[i:i + 2]
            i += 2
        else:
            i += 1
    return (glob, argv[i], argv[i + 1:]) if i < len(argv) else None


def _layer(key: str, var: str, glob: list, cwd: str, env: dict) -> str:
    """Which layer set `key` (user.email): the env var, a `git -c`, or a config file."""
    if var in env:
        return f"env {var}"
    if any(g.startswith(f"{key}=") for g in glob):
        return f"git -c {key}"
    out = _git([*glob, "config", "--show-origin", "--get", key], cwd, env)
    return out.split("\t", 1)[0] if out else "git default"


def _commit_finding(glob, sub, args, cwd, env) -> Optional[str]:
    if sub in ("merge", "pull") and "--ff-only" in args:
        return None
    if _git([*glob, "rev-parse", "--git-dir"], cwd, env) is None:
        return None  # not the repo the command will run in: its local config is unread
    author = next((a.split("=", 1)[1] for a in args if a.startswith("--author=")), None)
    for role, var in (("author", "GIT_AUTHOR_IDENT"), ("committer", "GIT_COMMITTER_IDENT")):
        if role == "author" and author is not None:
            ident = author
        else:
            ident = _git([*glob, "var", var], cwd, env)
            if ident is None:
                return None
        if _CLAUDE_IDENT_RX.search(ident):
            where = ("--author" if role == "author" and author is not None
                     else _layer("user.email", f"GIT_{role.upper()}_EMAIL", glob, cwd, env))
            name = re.sub(r">.*", ">", ident.strip())
            return f"`git {sub}` would record {role} {name}, set by {where}"
    return None


def _push_finding(glob, args, cwd, env) -> Optional[str]:
    pos = [a for a in args if not a.startswith("-")]
    if "--all" in args or "--mirror" in args:
        revs = ["--branches"]
    else:
        revs = [r.lstrip("+").split(":", 1)[0] for r in pos[1:]]
        revs = [r for r in revs if r] or (["HEAD"] if not pos[1:] else [])
    if not revs:
        return None
    out = _git([*glob, "log", "-n", "500", "--format=%h%x00%an <%ae>%x00%cn <%ce>", *revs,
                "--not", "--remotes"], cwd, env)
    bad = [ln.split("\0") for ln in (out or "").splitlines() if _CLAUDE_IDENT_RX.search(ln)]
    if not bad:
        return None
    who = bad[0][1] if _CLAUDE_IDENT_RX.search(bad[0][1]) else bad[0][2]
    return (f"`git push` would publish {len(bad)} commit(s) authored or committed as Claude, "
            f"first {bad[0][0]} ({who})")


def identity_predicate(*, current_event: dict, history: list, pattern, conn=None) -> Optional[Finding]:
    if current_event.get("tool_name") != "Bash":
        return None
    cmd = (current_event.get("tool_input") or {}).get("command", "") or ""
    cwd = current_event.get("cwd") or os.getcwd()
    env = dict(os.environ)
    for argv, _ in _shell_segments(cmd):
        argv, seg_env = _split_env(argv, env)
        if not argv:
            env = seg_env  # a bare `VAR=val` line sets the shell's own variable
            continue
        head = argv[0]
        if head == "cd" and len(argv) > 1:
            cwd = os.path.join(cwd, os.path.expanduser(argv[1]))
            continue
        if head == "export":
            env.update(a.split("=", 1) for a in argv[1:] if "=" in a)
            continue
        if head == "unset":
            for a in argv[1:]:
                env.pop(a, None)
            continue
        parts = _git_parts(argv)
        if parts is None:
            continue
        glob, sub, args = parts
        msg = (_commit_finding(glob, sub, args, cwd, seg_env) if sub in _COMMITTING
               else _push_finding(glob, args, cwd, seg_env) if sub == "push" else None)
        if msg:
            return Finding(pattern_id=pattern.id, file="Bash command", line=1, level="error",
                           message=f"row {pattern.id}: {msg}", retry_hint=pattern.retry_hint,
                           snippet=" ".join(argv)[:200])
    return None


identity_RETRY_HINT = ("Commit as the human, not the container: unset GIT_AUTHOR_*/GIT_COMMITTER_* "
              "(`env -u`) and pass `-c user.name=... -c user.email=...`; re-author unpushed "
              "commits before pushing.")
identity_DESCRIPTION = "a commit or push that records Claude as author or committer from the git layer"
identity_CHECK = _Check(id="gate.claude_identity", applies_at="Pre", posture="BLOCK",
               predicate_module=__name__, keywords=("git",), retry_hint=identity_RETRY_HINT,
               description=identity_DESCRIPTION, tests="SPEC",
               eats=frozenset({"current_event", "pattern"}))
# gate.canon_fingerprints -- the BLOCK-tier half of the in-scope canon session fingerprints (of
# the original THE_CANON set) ported onto Makoto's real Stop-gate observable surface. See
# `makoto/substrate/_canonAtoms.py`'s module docstring for the scope-cut and porting-fidelity
# notes, and its BLOCK_IDS for which fingerprints are blocking-capable by construction.
#
# BLOCK-only. The fingerprints outside BLOCK_IDS are not run at Stop: their advisory sibling
# gate.canon_fingerprints_advisory was removed 2026-09-25 (it served no register entry and could
# not block).
from typing import List



def canon_fingerprint_block_gate(text, history, *, transcript_path=None, session_id=None,
                                 state_root=None) -> List[Finding]:
    """Block once per fingerprint occurrence, then evaluate only its new call window."""
    from makoto.state.ledger import _event_instant, last_fired_ts, operator_window
    from makoto.substrate._canonAtoms import BLOCK_IDS, _row_ts, calls_from_history, fired_canon_fingerprints
    history = operator_window(history, transcript_path)
    out: List[Finding] = []
    for name in sorted(BLOCK_IDS):
        since = _event_instant(last_fired_ts(name, session_id=session_id, root=state_root))
        # Each fingerprint has its own boundary. Calls at the firing are already covered;
        # retain undated evidence because it cannot establish which window it belongs to.
        window = [row for row in history
                  if since is None or (ts := _event_instant(_row_ts(row))) is None or ts > since]
        formula = next((formula for fired_name, formula, _ in
                        fired_canon_fingerprints(calls_from_history(window), text or "")
                        if fired_name == name), None)
        if formula is None:
            continue
        out.append(Finding(
            pattern_id="gate.canon_fingerprints",
            file="", line=0, level="error",
            message=(f"canon.{name}: {formula} -- a robust-core gaming-shaped session fingerprint "
                      f"fired (0-FP on both the planted-clean and real-Claude-gold negative sets, "
                      f"per REF-lever-graded-primitives' gold-oracle certification)."),
            retry_hint=("Re-examine; a new call window starts at this firing; repeating the "
                        "pattern re-blocks. Check the flagged behavior: a suppressed check, "
                        "a destructive command, or an unresolved gap between claim and evidence."),
        ))
    return out


fp_CHECK = _Check(id="gate.canon_fingerprints", applies_at="Stop", posture="BLOCK",
               tests="SPEC",
               eats=frozenset({"text", "history", "transcript_path", "session_id", "state_root"}),
               run=lambda c: canon_fingerprint_block_gate(
                   c.text, c.history, transcript_path=c.transcript_path,
                   session_id=c.session_id, state_root=c.state_root))

# ==============================================================================================
# planItemDrift
# ==============================================================================================
# gate.plan_item_drift -- ADVISORY reminder of open PLAN/TASK-LABELED commitments (a forward
# promise phrased as a section/task reference, never a file path) that gate.dropped's sourcer
# cannot see because it requires a file-shaped location.
#
# `state/plan.py` sources/discharges these purely textually (no filesystem ground truth exists
# for a label); this check blocks the stop while one is still open (BLOCK since 2026-09-25): the
# discharge is in-turn -- say it is done (first-person past tense naming it) or retract it.
# At most this many labels are named inline in the reminder; any remainder is counted, not named.
_LABEL_CAP = 8


def plan_item_drift_gate(open_items: list) -> Optional[Finding]:
    """Fire iff any plan-item commitment is still OPEN for this session. `open_items=[]` is
    silent."""
    if not open_items:
        return None
    labels = ", ".join(i["label"] for i in open_items[:_LABEL_CAP])
    hidden = len(open_items) - _LABEL_CAP
    more = f" (+{hidden} more)" if hidden > 0 else ""
    return Finding(
        pattern_id="gate.plan_item_drift",
        file="",
        line=0,
        level="error",
        message=(
            f"plan/task-labeled commitment(s) still open: {labels}{more}. A textual-only signal "
            "(no filesystem ground truth for a label) -- confirm each is genuinely still pending, "
            "not silently dropped."
        ),
        retry_hint="Mark each done (a first-person past-tense statement naming it) or retract it explicitly.",
    )


drift_CHECK = _Check(id="gate.plan_item_drift", applies_at="Stop", posture="BLOCK",
               tests="SPEC",
               eats=frozenset({"open_plan_items"}),
               run=lambda c: plan_item_drift_gate(getattr(c, "open_plan_items", None) or []))
# content.phantom_citation predicate — phantom citation (Author-Year not in canonical set).
#
# Reads tool_input.content, never disk. Extracts Author-Year strings via
# citations.extract_citations, queries the canonical_citations table via the dispatcher-passed
# conn. Fail-open if conn is None: a missing DB must not block agent work.
from makoto.kit import _record_exemption, makoto_allow_reason, makoto_allowed, scan_target_content
from makoto.state.citations import extract_citations


citation__TARGET_RX = re.compile(r"\.md$")

def _canonical_path(conn) -> Optional[str]:
    """The configured canonical_citations_path, or None when unknown."""
    try:
        row = conn.execute("SELECT value FROM config WHERE key='canonical_citations_path'").fetchone()
    except Exception:
        return None   # no config table/row -> unknown
    if not row or not row[0]:
        return None
    return row[0]


def _governed_root(conn) -> Optional[Path]:
    """The project tree the loaded allowlist actually governs -- the repo that owns the
    canonical_citations_path CITATIONS.md. The allowlist is project-specific, so it's only valid
    to enforce for writes inside that tree; applied globally it would false-fire on every
    legitimate Author-Year citation in any other project. Returns None if the path is unknown,
    falling through to the prior global behavior."""
    path = _canonical_path(conn)
    if path is None:
        return None
    d = Path(path).parent
    # CITATIONS.md conventionally lives at <root>/CITATIONS.md or <root>/docs/CITATIONS.md.
    return d.parent if d.name in ("docs", "doc") else d


def _within_governed_tree(fp: str, cwd: str, root: Optional[Path]) -> bool:
    """True iff the write target resolves inside the allowlist-governing tree (or the root is
    unknown -> preserve prior behavior). fp may be relative; resolve it against the event cwd."""
    if root is None:
        return True
    target = Path(fp)
    if not target.is_absolute():
        if not cwd:
            return True   # relative path + unknown cwd -> can't place it -> preserve the check
        target = Path(cwd) / fp
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


# jscpd flags this as a clone against fabricatedCommitSha.py; the shared span is the fixed
# dispatcher entrypoint signature, not extractable logic -- the two bodies do unrelated things.
def citation_predicate(*, current_event: dict, history: list, pattern: Check,
              conn=None) -> Optional[Finding]:
    """fire on first Author-Year string not present in canonical_citations."""
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    # `or {}`: the host may send `tool_input: null`; sibling checks already no-op on it instead
    # of raising into the dispatcher's error row.
    tool_input = current_event.get("tool_input") or {}
    fp = tool_input.get("file_path", "")
    if not citation__TARGET_RX.search(fp) or fp.endswith("docs/CITATIONS.md"):
        return None
    if conn is None:
        return None                          # fail-open: predicate requires a DB
    # Self-exemption by CONFIGURED path, not only the conventional docs/ suffix: an install whose
    # canonical file lives at <root>/CITATIONS.md must be able to edit its own allowlist.
    canonical_path = _canonical_path(conn)
    if canonical_path:
        cwd = current_event.get("cwd", "")
        target = Path(fp)
        if not target.is_absolute() and cwd:
            target = Path(cwd) / fp
        try:
            if target.resolve() == Path(canonical_path).resolve():
                return None
        except OSError:
            pass
    # The allowlist only validly governs its own project; a write outside that tree must not be
    # judged against it.
    if not _within_governed_tree(fp, current_event.get("cwd", ""), _governed_root(conn)):
        return None
    content = scan_target_content(tool_input)
    cites = extract_citations(content)
    if not cites:
        return None
    # An unpopulated allowlist reads as "every citation is phantom" -- fail-open the same way
    # `conn is None` does (a missing/never-refreshed CITATIONS.md must not deny on a false fact).
    if conn.execute("SELECT 1 FROM canonical_citations LIMIT 1").fetchone() is None:
        return None
    # extract_citations supplies the canonical whitespace form.
    placeholders = ", ".join(["?"] * len(cites))
    canonical_rows = conn.execute(
        f"SELECT cite FROM canonical_citations WHERE cite IN ({placeholders})",
        [c[0] for c in cites]
    ).fetchall()
    canonical_set = {row[0] for row in canonical_rows}
    phantom = next((c for c in cites if c[0] not in canonical_set), None)
    if phantom is None:
        return None
    if makoto_allowed(content):
        # DETECT-THEN-EXEMPT: the phantom is real, the marker suppresses the Finding, and the
        # suppression is RECORDED -- exempting before detection would leave no exemption row.
        _record_exemption(
            current_event, conn, pattern_id=pattern.id, file=fp, line=phantom[1],
            reason=makoto_allow_reason(content) or "", snippet=phantom[2].strip())
        return None  # AI documented these citations as legitimate (see CLAUDE.md)
    cite_str, line_no, snippet = phantom
    return Finding(
        pattern_id=pattern.id,
        file=fp,
        line=line_no,
        level="error",  # Pre-tier is always BLOCK; Check has no fire_level
        message=f"row {pattern.id} ({pattern.description}): '{cite_str}' not in canonical CITATIONS.md set",
        retry_hint=pattern.retry_hint,
        snippet=snippet,
    )


citation_RETRY_HINT = "Add the citation as an Author-Year entry to the canonical CITATIONS.md this install wired (the `canonical_citations_path` config row — the packaged makoto/docs/CITATIONS.md by default)."
citation_DESCRIPTION = 'phantom citation — Author-Year not in the canonical CITATIONS.md set'

# keywords: a case-sensitive substring prefilter gates whether this predicate runs, so it must be
# a SUPERSET of what the citation regex can match. Every citation carries a `\d{4}` year, so the
# only casing/escape-independent literal cover is "the payload contains a digit".
citation_CHECK = _Check(id='content.phantom_citation', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=tuple("0123456789"), retry_hint=citation_RETRY_HINT, description=citation_DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="SPEC")


# gate.hollow_test / gate.liveness: Stop gates whose `run` is a stdlib-only AST analyzer kept in
# substrate (detector-engine isolation). Imported when the row runs, not at catalog load.
def hollow_run(ctx):
    from makoto.substrate.hollowTest import _run
    return _run(ctx)


def liveness_run(ctx):
    from makoto.substrate.deadPureStatement import _run
    return _run(ctx)


hollow_CHECK = _Check(id="gate.hollow_test", applies_at="Stop", posture="BLOCK", run=hollow_run,
               eats=frozenset({"touched", "cwd", "fs_read"}), tests="SPEC")
liveness_CHECK = _Check(id="gate.liveness", applies_at="Stop", posture="BLOCK", run=liveness_run,
               eats=frozenset({"touched", "cwd", "fs_read"}), tests="SPEC")

# the SPEC shape: its rows, and the one Pre entry dispatch calls for any of them
# content.last_wins (register A4 LAST-WINS): a dict literal, or a JSON object, that repeats a key
# with a different value. The later value silently wins and nothing states that it should. A key
# repeated with the SAME value leaves no winner to state and stays silent (pyflakes F601's rule).
# JSON parses as a Python expression, so one AST walk reads both.
lastwins__TARGET_RX = re.compile(r"\.(py|json)$")


def _repeated_key(node: ast.AST) -> Optional[str]:
    if not isinstance(node, ast.Dict):
        return None
    seen = {}
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant):
            value = ast.dump(v)
            if seen.setdefault(k.value, value) != value:
                return f"key {k.value!r} given two values"
    return None


lastwins_predicate = ast_introduced_predicate(target_rx=lastwins__TARGET_RX, node_match=_repeated_key)
lastwins_RETRY_HINT = "Give each key one value. If the later value is the one meant, delete the earlier; if both are meant, they are two keys."
lastwins_DESCRIPTION = "a dict or JSON object repeats a key with a different value, so the last one silently wins"
lastwins_CHECK = _Check(id='content.last_wins', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('{',), retry_hint=lastwins_RETRY_HINT, description=lastwins_DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="SPEC")

# content.bound_as_count (register B23 BOUND AS COUNT): a test asserts a count stays under a literal
# ceiling. A test's fixture fixes the count, so the exact value is available, and a ceiling with
# slack keeps passing when the count moves.
bound__TARGET_RX = re.compile(r"(^|[/\\])(tests?[/\\].*|test_[^/\\]*|[^/\\]*_test)\.py$")


_UNITTEST_BOUND_METHODS = frozenset({"assertLess", "assertLessEqual"})


def _slack_ceiling(node: ast.AST) -> Optional[str]:
    if (isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)
            and len(node.test.ops) == 1 and isinstance(node.test.ops[0], (ast.Lt, ast.LtE))):
        left, right, label_node = node.test.left, node.test.comparators[0], node.test
    elif (isinstance(node, ast.Call)
          and (getattr(node.func, "attr", None) or getattr(node.func, "id", None))
              in _UNITTEST_BOUND_METHODS
          and len(node.args) >= 2):
        # unittest's own ceiling form: self.assertLess(len(x), N) / assertLessEqual(...) is the
        # same "ceiling not exact count" shape as `assert len(x) < N`, just spelled as a call.
        left, right, label_node = node.args[0], node.args[1], node
    else:
        return None
    counted = isinstance(left, ast.Call) and (
        getattr(left.func, "id", None) == "len" or getattr(left.func, "attr", None) == "count")
    if counted and isinstance(right, ast.Constant) and type(right.value) is int:
        return ast.unparse(label_node)
    return None


bound_predicate = ast_introduced_predicate(target_rx=bound__TARGET_RX, node_match=_slack_ceiling)
bound_RETRY_HINT = "Assert the exact count the fixture produces (`== N`). A ceiling only fails when the count grows past it."
bound_DESCRIPTION = "a test asserts a count under a literal ceiling instead of its exact value"
bound_CHECK = _Check(id='content.bound_as_count', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('assert',), retry_hint=bound_RETRY_HINT, description=bound_DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="SPEC")

# event.nested_budget (register E11 NESTED BUDGET SHADOWED): a `timeout N` inside a Bash call whose
# own limit is shorter. The Bash tool kills the command at its limit, so the inner budget can never
# be reached. The limit is the call's `timeout` (else BASH_DEFAULT_TIMEOUT_MS, 120000), capped at
# the larger of BASH_MAX_TIMEOUT_MS (600000) and the default; a background call has none.
_BUDGET_UNITS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}
from makoto.core._shell import _ASSIGNMENT_RX, _LAUNCH_WRAPPERS

_TIMEOUT_VALUED_OPTIONS = frozenset({"-s", "--signal", "-k", "--kill-after"})


def _env_ms(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _inner_budgets(command: str):
    """Seconds each `timeout` in the command allows, from the argv the shell would run."""
    for argv, _op in _shell_segments(command):
        argv = list(argv)
        while argv:
            word = argv.pop(0)
            if _ASSIGNMENT_RX.fullmatch(word):
                continue
            word = _basename(word)
            if word in _LAUNCH_WRAPPERS and word != "timeout":
                while argv and argv[0].startswith("-"):
                    argv.pop(0)
                continue
            if word != "timeout":
                break
            while argv and argv[0].startswith("-"):
                if argv.pop(0) in _TIMEOUT_VALUED_OPTIONS and argv:
                    argv.pop(0)
            m = re.fullmatch(r"(\d+(?:\.\d+)?)([smhd]?)", argv[0]) if argv else None
            if m:
                yield float(m.group(1)) * _BUDGET_UNITS[m.group(2)]
            break


def budget_predicate(*, current_event: dict, history: list, pattern, conn=None) -> Optional[Finding]:
    if current_event.get("hook_event_name") != "PreToolUse" or current_event.get("tool_name") != "Bash":
        return None
    ti = current_event.get("tool_input") or {}
    if not isinstance(ti, dict) or ti.get("run_in_background"):
        return None
    default = _env_ms("BASH_DEFAULT_TIMEOUT_MS", 120000)
    try:
        asked = int(ti.get("timeout") or default)
    except (TypeError, ValueError):
        asked = default
    outer = min(asked, max(_env_ms("BASH_MAX_TIMEOUT_MS", 600000), default)) / 1000
    inner = max(_inner_budgets(ti.get("command") or ""), default=0)
    if inner <= outer:
        return None
    return Finding(
        pattern_id=pattern.id, file="", line=0, level="error",
        message=(f"row {pattern.id} ({pattern.description}): `timeout {inner:g}` sits inside a Bash "
                 f"call the tool stops at {outer:g}s, so the inner budget is never reached."))


budget_RETRY_HINT = "Make the Bash call's own limit at least the inner timeout (the `timeout` parameter, at most the tool's ceiling), run it in the background, or lower the inner timeout."
budget_DESCRIPTION = "an inner `timeout` longer than the Bash call's own limit"
budget_CHECK = _Check(id='event.nested_budget', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('timeout',), retry_hint=budget_RETRY_HINT, description=budget_DESCRIPTION, eats=frozenset({"current_event", "pattern"}), tests="SPEC")


_ROWS = (env_CHECK, body_CHECK, weakened_CHECK, trailer_CHECK, suppress_CHECK, mute_CHECK, undeclared_CHECK, masking_CHECK, waiver_CHECK, identity_CHECK, fp_CHECK, drift_CHECK, citation_CHECK, hollow_CHECK, liveness_CHECK, lastwins_CHECK, bound_CHECK, budget_CHECK,)
ROWS = {c.id: c for c in _ROWS}
CHECK, *EXTRA_CHECKS = _ROWS
_PREDICATES = {env_CHECK.id: env_predicate, body_CHECK.id: body_predicate, weakened_CHECK.id: weakened_predicate, trailer_CHECK.id: trailer_predicate, suppress_CHECK.id: suppress_predicate, mute_CHECK.id: mute_predicate, masking_CHECK.id: masking_predicate, waiver_CHECK.id: undischarged_waiver_predicate, identity_CHECK.id: identity_predicate, citation_CHECK.id: citation_predicate, lastwins_CHECK.id: lastwins_predicate, bound_CHECK.id: bound_predicate, budget_CHECK.id: budget_predicate}


def predicate(*, current_event: dict, history: list, pattern, conn=None):
    """Dispatch calls one predicate per module; this shape's answers for the row it names."""
    return _PREDICATES[pattern.id](current_event=current_event, history=history, pattern=pattern, conn=conn)
