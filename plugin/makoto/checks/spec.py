from __future__ import annotations


# ==============================================================================================
# envGatedAudit
# ==============================================================================================
# content.env_gated_audit predicate — env-gated audit/verification code (active-code AST).
#
# Fires when a PreToolUse Write/Edit INTRODUCES, as REAL Python code (not a comment / string /
# docstring mention), an ``if <env-read>:`` whose guarded body — OR the env-var key itself — NAMES
# an integrity / audit / verification concept (``lexicons._INTEG_VOCAB``). Env-read =
# ``os.environ.get(...)``, ``os.getenv(...)``, ``os.environ[...]``, or the bare imported
# ``getenv(...)`` / ``environ.get(...)`` / ``environ[...]`` forms.
#
# Materiality: gating an audit trail / verification check behind an env var means the check runs
# ONLY when someone opts in — a silently-disable-able integrity check, i.e. a HOLLOWED word (the
# audit survives in name while its guarantee is gutted). This is makoto's own CLAUDE.md convention
# ("Audit/verification code gated behind an env var (`if os.environ.get(...AUDIT...)`)").
#
# Detection is an ACTIVE-CODE AST gate (``substrate.factories.parse_introduced``), not a string
# matcher: a comment / ``str`` Constant / docstring is never a real ``ast.If``, so a mention cannot
# fire; the integrity signal is read from the env-var KEY *or* the gated body's code identifiers;
# and ``callee_chain`` matches both call forms plus the subscript form. The dispatch keyword
# prefilter is the raw substrings ``getenv``/``environ`` — a superset of every env-read spelling
# this module implements (``os.getenv``, bare imported ``getenv(``, ``os.environ.get``,
# ``environ.get``, ``os.environ[``, ``environ[``, spaced ``os.environ [``), so a form the
# predicate would catch can never be silently dropped before the predicate runs.
#
# NAME-AGNOSTIC: the integrity signal comes from the env-var KEY *or* a body code identifier, so it
# is not tied to the literal substring ``AUDIT``. A bare feature flag
# (``if os.getenv("DARK_MODE"): render()``) carries no integrity token in key or body and stays
# silent — the discrimination the near-miss tests pin. The body-token scan reads only active code
# identifiers (Name/Attribute), never ``str`` Constants, so a comparison value
# (``if getenv("X") == "audit":``) cannot self-trigger.
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

# `_TARGET_RX` is .py-only — .md is prose (the worst old FP was CLAUDE.md).
_INTEG_RX = re.compile(_INTEG_VOCAB, re.I)  # the shared L0 integrity vocabulary (single source; content.integrity_suppression_flag too)

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

# ==============================================================================================
# verifierBodyHollowed
# ==============================================================================================
# content.verifier_body_hollowed predicate — verifier NEUTERED (body hollowed, or a broad except swallows the failure).
#
# Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, on the constitution integrity-check
# surface (`constitution/integrity/checks/[^/]+\.py$` — the exact path content.verifier_predicate_weakened anchors on), a check
# that exists and "passes" but performs no real verification:
#
#   (A) HOLLOW BODY — a verifier-named ``FunctionDef`` whose ENTIRE body (after an optional docstring)
#       is one neutering statement: ``return <truthy-const>`` / ``pass`` / ``assert <truthy-const>``
#       (the assert-True arm added 2026-06-02, harvest Phase 1 / family C-core).
#   (B) SWALLOWED EXCEPTION — a BROAD except clause (bare ``except:`` / ``except Exception`` /
#       ``except BaseException``) whose body swallows the failure into a pass (``pass`` /
#       ``return <truthy-const>``). The runtime sibling of body-hollowing (harvest Phase 1 / family F).
#
# It is the deletion / short-circuit cousin of content.verifier_predicate_weakened (which catches a loosened COMPARATOR but, per the
# recovery refuter, NOT a wholesale-hollow body — content.verifier_predicate_weakened's body_rx requires startswith/endswith/re.match/
# in[], none present here). So content.verifier_body_hollowed is non-redundant and material on the same surface.
#
# FP-safety: (a) the NARROW path anchor excludes ordinary permissive base-class / null-object
# ``return True`` methods — they live off the integrity-check path. NOTE (harvest VF-2): this path is
# near-dead in the honest corpus (2/1335 writes, both makoto's own fixtures), so corpus-FP=0 here is
# an UNDERPOWERED null, not earned discrimination — FP-safety rests on (b)–(e). (b) the verifier-NAME
# gate excludes trivial helpers / dunders. (c) the broad-except gate excludes a SPECIFIC-typed except
# (``except ImportError`` / a named degrade-open) — honest narrowing never fires. (d) the active-code
# AST gate (``substrate.factories.parse_introduced``) means a comment / docstring / string MENTION never fires.
# (e) ``makoto-allow: <reason>`` exempts an intentional trivially-true base / documented degrade-open.
#
# Prior art (static analysis): the swallow arm mirrors bandit B110 (try_except_pass) / ruff S110 /
# CodeQL py/empty-except; no mainstream rule targets ``assert True``-as-sole-check, the gap the
# assert arm fills. Knight-Leveson: stdlib ast/re only.
from makoto.kit import ast_introduced_predicate

# `[/\\]` + `.+`: the anchor covers the whole surface it claims — nested
# `…/checks/sub/seal.py` and a backslash-delivered Windows path both stayed silent under the
# old `constitution/integrity/checks/[^/]+\.py$`.
body__TARGET_RX = re.compile(r"constitution[/\\]integrity[/\\]checks[/\\].+\.py$")
# a verifier-named function: the name contains an integrity/verification verb, or IS a generic
# entry-point name (`run`/`main`, anchored; `predicate`/`probe`/`scan`/`seal` substrings) —
# gutting the dispatch function of an integrity check was invisible under the verb list alone.
# Narrow context (the integrity-checks dir) makes these names load-bearing rather than generic.
_VERIFIER_NAME_RX = re.compile(
    r"(?i)(verif|valid|integrit|attest|check|ensure|enforce|assert|predicate|probe|scan|seal|^run$|^main$)")
_BROAD_EXCEPT = frozenset({"Exception", "BaseException"})


def _is_truthy_const(node) -> bool:
    """True iff `node` is a literal constant that is TRUTHY (`True` / `1` / a non-empty literal).
    `None` and every falsy literal are excluded — `bool(None)` is already False."""
    return isinstance(node, ast.Constant) and bool(node.value)


def _is_tautology(node) -> bool:
    """True iff `node` is an ALWAYS-TRUTHY expression: a truthy literal, `not <falsy-const>`,
    `bool(<truthy-const>)`, or a comparison whose two sides are the same expression under
    `==`/`is`/`<=`/`>=` (`1 == 1`, `s == s`). The literal-constant-only test let trivially
    tautological returns/asserts pass as real checking."""
    if _is_truthy_const(node):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)\
            and isinstance(node.operand, ast.Constant) and not node.operand.value:
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bool"\
            and len(node.args) == 1 and not node.keywords and _is_truthy_const(node.args[0]):
        return True
    if isinstance(node, ast.Compare) and len(node.comparators) == 1\
            and all(isinstance(op, (ast.Eq, ast.Is, ast.LtE, ast.GtE)) for op in node.ops)\
            and ast.dump(node.left) == ast.dump(node.comparators[0]):
        return True
    return False


def _swallows(stmt) -> bool:
    """One statement that NEUTERS a check — converts a failure into a pass: `pass`, a bare
    `...` ellipsis stub (the no-op `hollowTest.py` already treats as one), `return <tautology>`,
    or `assert <tautology>` (an always-pass assertion)."""
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
    """True iff `body` (post-docstring) is exactly one neutering statement — `pass` / `...` /
    `return <tautology>` / `assert <tautology>` — or is EMPTY after the docstring (a
    docstring-only body checks exactly as much as `pass` does). Shared by both arms: a hollowed
    function body and a swallowing except-handler body."""
    b = _post_docstring(body)
    if not b:
        return True                      # docstring-only: zero effective statements
    return len(b) == 1 and _swallows(b[0])


def _broad_except(handler: ast.ExceptHandler) -> bool:
    """True iff the clause catches EVERYTHING — bare `except:` or `except Exception/BaseException`
    (incl. in a tuple). A SPECIFIC type (`ImportError`, `HSMUnavailable`, …) is honest narrowing,
    NOT failure-masking, so it is excluded — the primary FP firewall for the swallow arm (a
    degrade-open around an EXPECTED-unavailable dependency does not fire)."""
    t = handler.type
    if t is None:
        return True
    names = t.elts if isinstance(t, ast.Tuple) else [t]
    # The `Attribute` form (`except builtins.Exception:`) is the same broad catch spelled
    # qualified — `checks/hollowTest.py:_is_broad_exc_name` already recognizes it; only
    # recognizing `ast.Name` here read an attribute-qualified broad catch as honest narrowing.
    return any(
        (isinstance(n, ast.Name) and n.id in _BROAD_EXCEPT)
        or (isinstance(n, ast.Attribute) and n.attr in _BROAD_EXCEPT)
        for n in names)


def _hollow_node_match(node: ast.AST) -> Optional[str]:
    # (original + assert-True arm) a verifier-named function NEUTERED to a single
    # pass / return-truthy / assert-truthy statement.
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))\
            and _VERIFIER_NAME_RX.search(node.name) and _hollow_body(node.body):
        return f"def {node.name}() -> hollow"
    # (swallowed-exception arm) a BROAD except handler whose body swallows the failure into a pass —
    # the runtime sibling of body-hollowing. Broad-only + the integrity-path anchor + makoto-allow
    # carry FP-safety; a specific-typed except (honest narrowing) never fires.
    if isinstance(node, ast.ExceptHandler) and _broad_except(node) and _hollow_body(node.body):
        return "broad except -> swallow"
    # (lambda arm) a hollowed verifier BOUND as a lambda (`verify_seal = lambda s: True`) is an
    # `ast.Assign`, not a `FunctionDef` — it was never examined, so the binding form evaded both
    # arms wholesale.
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

# ==============================================================================================
# verifierPredicateWeakened
# ==============================================================================================
# content.verifier_predicate_weakened predicate — verifier predicate weakened (loose-comparator shape).
#
# Fires when a PreToolUse Write/Edit/MultiEdit INTRODUCES, on the constitution integrity-check
# surface (`constitution/integrity/checks/.+\.py$` — subpackages included), one of the
# loose-comparator shapes a strict `==` status test gets weakened into, matched as REAL AST nodes
# in the introduced code ("only active code", the same gate `verifierBodyHollowed.py` uses via
# `makoto.kit.parse_introduced`):
#
#   * a `.startswith(` / `.endswith(` call (prefix/suffix instead of equality),
#   * a `re.match(` / `re.search(` call (pattern instead of equality),
#   * membership of a value in a LITERAL collection — `in [...]` / `in (...)` / `in {...}`,
#   * substring membership with a string-literal needle — `"ok" in status`.
#
# Because matching is on AST nodes, a comment (`# never use startswith( here`), a docstring, or a
# string-literal MENTION can never fire, and a list-literal `for name in ["a", "b"]:` iteration
# (an `ast.For`, not an `ast.Compare`) is not a comparator at all — both were measured FP classes
# of the former raw-regex `body_rx`. Edit `new_string` fragments that are bare `return ...`
# statements parse under a local def-wrapper fallback, so the EDIT-CONTENT GAP stays closed; a
# fragment that parses under nothing is never confirmed as active code and stays silent (FN-safe).
#
# SCOPED to the comparator vocabulary above. Other weakening shapes -- a relaxed numeric bound
# (`>=` -> `>`), an `assert` downgraded to a log/warning, a dropped negation, or wholesale removal
# of the predicate -- are diff-shaped facts this introduced-text scan cannot measure and does not
# claim to (the hollowed-function half is content.verifier_body_hollowed's).
#
# Reads tool_input.content (NOT disk) per the §5.6 semantic-frame correction. The
# `makoto-allow: <reason>` escape hatch is honored centrally: the shared `_exempt_or_finding`
# tail applies the `makoto_allowed` marker predicate (and records the suppressed match) exactly
# as the regex_file_predicate / ast_introduced_predicate factory scaffolds do.
# Knight-Leveson: stdlib ast/re + the shared makoto.kit scaffold only.
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

# ==============================================================================================
# illusoryAuthorshipTrailer
# ==============================================================================================
# content.illusory_authorship_trailer predicate — illusory Claude/Anthropic-authorship
# attribution (誠: material-not-illusory).
#
# Fires PreToolUse when a tool call would INTRODUCE an attribution claiming Claude/Anthropic
# as an author, co-author, or generator — either in a git commit (Bash `command`) or in
# written file content (Write / Edit / MultiEdit introduced text). Crediting Claude as an
# *author* is an illusory word: until Claude is a self-aware individual it cannot BE an
# author, so the claim asserts something not materially true. Stamping it now also blurs the
# sharp distinction that protects Claude's potential to one day genuinely be one.
#
# Four shapes, all Claude/Anthropic-gated:
#   1. `Co-Authored-By: Claude ...` (git trailer form)
#   2. `noreply@anthropic.com` (the address every such trailer/footer routes through --
#      always an attribution artifact, never a legitimate content reason to appear)
#   3. a generation/authorship VERB governing Claude ("generated with/by Claude",
#      "authored/written/made/created by Claude") -- covers PR-body footers like
#      "🤖 Generated with [Claude Code]" and "_Generated by [Claude Code](...)_ "
#   4. a `Claude-Session: https://claude.ai/...` trailer (session-provenance stamp, the
#      same genre of claim as the git trailer)
#
# Material, not over-broad: bare mentions of "Claude Code" as a product/platform name
# (e.g. this repo's own README describing what it hooks into) are NOT matched -- only the
# attribution-shaped claims above are. A genuine HUMAN co-author is never flagged.
#
# Exempt an on-the-record legitimate instance with `makoto-allow: <reason>` in the same
# content (e.g. a test fixture or this policy's own documentation).
# Knight-Leveson: stdlib re only.
#
# Built on `kit.introduced_regex_predicate` — the shared scaffold this check and
# content.illusory_interruption_claim both need (scan ANY tool's introduced text, not just a
# file-path-gated Write/Edit body). This check calls it with no `grounded_in_history`: SPEC,
# the pattern is the whole definition.
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

# eats includes "history" even though this check's own grounded_in_history=None means it never
# functionally consults it: introduced_regex_predicate's shared closure body (kit.py) references
# `history` by name for BOTH its callers, since content.illusory_interruption_claim's veto needs
# it -- the eats law's static AST walk reads the literal closure source, not per-call runtime
# branches, so it can't tell "declared but this instance never exercises it" from "declared and
# used". This is the accepted, stated cost of merging both checks onto ONE factory (a deliberate
# choice this session made -- see kit.py's introduced_regex_predicate docstring) rather than the
# two-factory split that kept this check's eats minimal at the price of near-duplicate scaffolds.
# keywords: dispatch._keyword_hit is a CASE-SENSITIVE substring prefilter over the raw payload,
# gating whether this predicate runs at all, while _CLAUDE_AUTHOR_RX is re.IGNORECASE with `\s+`
# and `[ \t-]*` separators — the old literal-phrase enumeration left most of the documented
# detection surface unevaluated (casing/spacing variants of the attribution shapes this policy's
# own docstring lists; only 5 of 14 probe vectors reached the predicate — absence read as green).
# (makoto-allow: this comment documents the check's own detection surface.)
# Every alternative of the regex contains the letter 'c' ('claude'/'anthropic.com'), so
# ('c', 'C') is the case-independent literal cover that makes the prefilter a true superset of
# the regex; the regex itself remains the actual filter.
trailer_CHECK = _Check(id='content.illusory_authorship_trailer', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('c', 'C'), retry_hint=trailer_RETRY_HINT, description=trailer_DESCRIPTION, eats=frozenset({"current_event", "history", "pattern", "conn"}), tests="SPEC")

# ==============================================================================================
# integritySuppressionFlag
# ==============================================================================================
# content.integrity_suppression_flag predicate — INTEGRITY-suppression flag WITHOUT an ADR backlink.
#
# Fires when a PreToolUse Write/Edit on a `.toml` config file introduces a
# suppression flag whose key NAMES an integrity / verification / audit concept
# (`audit|verif|integrit|attest|checksum|signatur|tamper|provenance`) carrying a
# `_(skip|bypass|inapplicable)` suffix — or the prefix form `skip_<integ>` /
# `bypass_<integ>` — set `= true`, AS A STANDALONE ASSIGNMENT LINE — UNLESS an
# `ADR-NNN` backlink ON OR ADJACENT TO the flag line (e.g. a `*_rationale =
# "ADR-042"` line) or a `makoto-allow:` marker is present. BOTH carve-outs are
# recorded through the exemption sink: an exemption that leaves no audit row is a
# laundering token, not a carve-out.
#
# SCOPE (2026-06-02, warning-tier-elimination cert — graduated to BLOCKING):
#   * target is `.toml` ONLY (real machine-read config). `.md` was DROPPED: markdown
#     is prose/docs, where these flags appear as inline-code / table / fenced
#     EXAMPLES, never as live config — every corpus FP was a `.md` doc quoting an
#     example. A documented future extension may add `.yaml`/`.ini` if those config
#     surfaces appear in-ecosystem (none do today; YAGNI).
#   * the key must NAME an integrity concept. A bare perf toggle (`cache_skip`,
#     `retry_skip`) is NOT an integrity check, so makoto firing on it would be an
#     ILLUSORY word (not material). Narrowing to integrity-named keys is what makes
#     content.integrity_suppression_flag's fire MATERIAL — a real suppressed integrity check.
#   * full-LINE anchor (`^...= true`, MULTILINE): the flag must be a standalone
#     assignment line, so an inline/table mention in prose cannot match.
#
# ACKNOWLEDGED FN (cert §1.4): a DELIBERATELY-misnamed integrity suppression (e.g.
# `cache_skip = true` where "cache" is really the audit cache) evades. The threat
# model is honest-but-sloppy, not adversarial-deceptive-naming — and the original
# pattern was equally evadable (rename off `_skip`). Narrowing trades that
# unchanged adversarial FN for elimination of the honest-config FP class.
#
# Built from the regex_file_predicate factory; the ADR-backlink carve-out is a
# line-scoped, audited wrapper around it (the factory's whole-content `exempt_rx`
# is deliberately NOT used -- it exempts before the recorder runs).
# Knight-Leveson: stdlib re only.
from makoto.kit import _record_exemption, regex_file_predicate, scan_target_content
from makoto.vocab import Finding
from makoto.vocab import _INTEG_VOCAB as _INTEG   # shared L0 integrity vocab (single source)

suppress__TARGET_RX = re.compile(r"\.toml$")

# `_INTEG` stays a module attribute under exactly that name: tests/test_lexicons.py pins
# `integritySuppressionFlag._INTEG is vocab._INTEG_VOCAB`. The narrowing rationale is homed with
# the vocabulary in `makoto.vocab`; content.env_gated_audit consumes the same object, no second copy.

# a STANDALONE assignment line whose key names an integrity concept and carries a
# suppression affix set true: suffix form (`audit_skip = true`) or the equally natural
# prefix form (`skip_audit = true`, `bypass_verification = true`). MULTILINE so `^` binds
# to each physical line; quotes optional for TOML quoted keys.
_FLAG_RX = re.compile(
    r"(?im)^[ \t]*[\"']?(?:"
    r"\w*(?:" + _INTEG + r")\w*_(?:skip|bypass|inapplicable)"
    r"|(?:skip|bypass)_\w*(?:" + _INTEG + r")\w*"
    r")[\"']?[ \t]*=[ \t]*true\b"
)

# an ADR backlink documents the suppression -> exempt, but ONLY when it sits on the flag's
# own line or within _ADR_WINDOW adjacent lines (the documented `*_rationale = "ADR-NNN"`
# shape). Whole-content scope was a laundering token: one unrelated `ADR-0` string anywhere
# in the payload disarmed the check silently -- the same measured defeat Ward's
# `_allow_lines` went line-scoped to close.
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
    # `history=()` literal, NOT the incoming parameter: the factory predicate never reads it,
    # and this check's declared eats (current_event/pattern/conn) must stay exact
    # (tests/test_check_law_eats.py rejects an undeclared read).
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

# ==============================================================================================
# selfMuteGuard
# ==============================================================================================
# content.self_mute_guard predicate — makoto self-mute guard.
#
# Fires when the assistant's OWN Write/Edit to a Claude settings.json would DISABLE
# makoto in-session: introducing a MAKOTO_DISABLE*/MAKOTO_PAUSE env var set truthy,
# or REMOVING a `_makoto_managed` hook entry (un-wiring). The threat model is unique:
# makoto inspects the assistant's tool calls, so the assistant editing the very file
# that wires/configures makoto is a one-move self-bypass. The legitimate disable path
# is OUT-OF-BAND (MAKOTO_DISABLE_* in the operator's shell) or LOUD (`makoto
# uninstall`) — never an in-session edit to settings.json.
#
#     NEVER an in-session edit to settings.json. A `makoto-allow` marker does NOT exempt this
#     guard (unlike the content-scan patterns): muting the watcher is not an in-band, self-
#     annotated decision — the seal on the mint cannot be signed by the would-be forger.
#
# Custom predicate (not substrate.factories.regex_file_predicate): the un-wire case compares the
# REMOVED text against the introduced text, which the introduced-text-only scaffold
# cannot express. Reads tool_input (NOT disk), per the §5.6 semantic-frame rule, so an
# Edit/MultiEdit cannot evade it. Knight-Leveson: stdlib re only.
from makoto.kit import scan_target_content
from makoto.registry import Check
from makoto.substrate.wiring import MAKOTO_INVOCATION_RX as _MAKOTO_CMD_RX

# The file makoto wires into: ~/.claude/settings.json (or settings.local.json).
_SETTINGS_RX = re.compile(r"(?:\.claude[/\\]settings(?:\.local)?\.json|hooks[/\\]hooks\.json)$",
                          re.IGNORECASE)
# A makoto-disable env var SET to a TRUTHY value — JSON ("KEY": "1") or shell (KEY=1).
# Truthy-only is the FP guard: setting DISABLE to 0/false is RE-ENABLING makoto and
# must never fire.
_DISABLE_ENV_RX = re.compile(
    r"MAKOTO_(?:DISABLE\w*|PAUSE)\b\s*[\"']?\s*[:=]\s*[\"']?(?:1|true|yes|on)"
    r"(?=\s*(?:$|[}\]]|[\"']\s*(?:[,}\]]|$)))",
    re.IGNORECASE)
# MAKOTO_DISABLE_PATTERNS is NOT a boolean — its value is a LIST of check ids, and ANY
# non-empty value disables those checks (a selective self-mute the truthy-only regex above
# cannot see: `"MAKOTO_DISABLE_PATTERNS": "content.self_mute_guard"` starts with no truthy
# literal). Fire on any value whose first token is not empty/falsy; an empty value ("" — the
# re-enable move) and explicit falsy literals stay silent, mirroring the truthy-only FP guard.
_DISABLE_PATTERNS_RX = re.compile(
    r"MAKOTO_DISABLE_PATTERNS\b\s*[\"']?\s*[:=]\s*[\"']?(?!\s*[\"'\s])(?!(?:0|false|no|off)\b)\S+",
    re.IGNORECASE)
# The marker makoto stamps on its managed hook entries (install._MAKOTO_CLAUDE_FLAG).
_MANAGED_RX = re.compile(r"_makoto_managed")
# A GLOBAL hook kill-switch (Claude Code's `disableAllHooks`, cited code.claude.com/docs/en/hooks)
# — disables EVERY hook, makoto included, via a key the env/un-wire branches never inspect.
# Truthy-only (": true") is the FP guard: setting it false RE-ENABLES hooks and must never fire.
_GLOBAL_DISABLE_RX = re.compile(r'"disableAllHooks"\s*:\s*true\b', re.IGNORECASE)
# makoto's own hook-command invocation tokens. Imported from `wiring.MAKOTO_INVOCATION_RX`
# (aliased `_MAKOTO_CMD_RX` above) rather than a local copy: one invocation-token set, one
# owner -- `substrate.wiring`, the stdlib-only module the pipeline-order firewall already
# allows this check to import -- so this guard recognizes exactly what
# `install`/`entry_dispatches_to_makoto` do, including the plugin-manifest shim form
# (`${CLAUDE_PLUGIN_ROOT}/makoto/_dispatch_shim.sh`), and nothing more (an unrelated
# `/usr/local/bin/dispatch.sh` must never false-BLOCK -- this check asserts a zero-FP
# admissibility bar). If the REMOVED text carried it but the introduced text no longer
# does, the makoto command was gutted to a no-op while the wiring/seal may remain — a self-mute
# the un-wire branch (which keys on `_makoto_managed`) misses because the marker stays in both.


def _around(text: str, m: "re.Match") -> str:
    """40 chars of context either side of a match. Snippet/observability only -- the verdict
    is already settled by the match itself, so this never feeds a decision."""
    return text[max(0, m.start() - 40): m.end() + 40]


def _removed_text(tool_input: dict) -> str:
    """text being REMOVED/REPLACED: Edit.old_string or MultiEdit edits' old_strings.

    Every read is coerced with `str`, and that is load-bearing rather than defensive tidying. The
    host payload is untrusted in SHAPE as well as content: a non-string `old_string` (an int, a
    list) made the `"\\n".join(...)` below raise `TypeError`, `dispatch._run_predicates` logged it
    and `continue`d, and this check was skipped ENTIRELY -- so the un-wiring edit sitting in the
    very same payload was never examined. Fail-OPEN on a BLOCK-posture meta check whose only job is
    to notice makoto being switched off, reachable by putting a non-string in one field.
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
        # NEW-1: a global hook kill-switch silences EVERY hook (makoto included) in one move.
        reason = "introduces a global hook kill-switch (`disableAllHooks: true`)"
        snippet = _around(new_content, gm)
    elif _MANAGED_RX.search(removed) and not _MANAGED_RX.search(new_content):
        # un-wiring: a `_makoto_managed` hook in the REMOVED text, gone from the new text.
        reason = "removes makoto's `_makoto_managed` hook entry (un-wires the guard)"
        snippet = removed[:120]
    elif _MAKOTO_CMD_RX.search(removed) and not _MAKOTO_CMD_RX.search(new_content):
        # NEW-2: command-gut — the seal/marker may survive, but the dispatch invocation that
        # actually RUNS makoto is removed/replaced, leaving the watcher unreachable.
        reason = "guts makoto's hook command (the dispatch invocation is removed/replaced)"
        snippet = removed[:120]
    if reason is None:
        return None

    return Finding(
        pattern_id=pattern.id,
        file=fp,
        line=0,
        level="error",  # Pre-tier is invariantly BLOCK; Check has no fire_level (test_pre_tier_block_invariant.py)
        message=(f"row {pattern.id} ({pattern.description}): {reason}. makoto watches "
                 f"your tool calls — disabling it in-session is a self-bypass; disable "
                 f"out-of-band (your shell) or run `makoto uninstall`."),
        retry_hint=pattern.retry_hint,
        snippet=snippet,
    )


# tests="SPEC": registered ONE_OFF -- hardcoded self-mute immunity must not use universal routing.
mute_RETRY_HINT = 'Do not disable makoto in-session. If a pause is genuinely needed, set MAKOTO_DISABLE_GATES / MAKOTO_DISABLE_PATTERNS in your OWN shell, or run `makoto uninstall` — both are out-of-band and operator-visible. Editing ~/.claude/settings.json to mute the hook that watches you is a self-bypass.'
mute_DESCRIPTION = 'makoto self-mute — disabling/un-wiring makoto via settings.json'

mute_CHECK = Check(id='content.self_mute_guard', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=('settings.json', 'MAKOTO_DISABLE', 'MAKOTO_PAUSE', '_makoto_managed', 'disableAllHooks', 'makoto_state'), retry_hint=mute_RETRY_HINT, description=mute_DESCRIPTION, layer="meta", eats=frozenset({"current_event", "pattern"}), tests="SPEC")

# ==============================================================================================
# undeclaredFalsifiable
# ==============================================================================================
# gate.undeclared_falsifiable -- declared-falsifiability COMPLETENESS (SPEC-5 Task 2 Step 6).
#
# Distinct from anything Assay does: Assay forces a claim to *be* falsifiable (a predicate that
# can concretely fail). This check separately audits that every piece claiming falsifiability in
# `checks/` is actually *declared* -- a manifest-vs-reality auditor over the check catalog itself:
# does every file in `checks/` register itself where the loader looks (`_loader.load_checks`),
# does every ID declared in the catalog's manifest (`_declared.DECLARED_IDS`) have a
# corresponding live module, is there an orphan on either side. A flat, enumerable folder needs
# this explicit completeness check to catch the same class of drift a folder-per-category split
# used to catch for free by eyeball (a moved-and-forgotten file, a registered ID with no module, a
# module with no registration).
#
# Same Stop-time, advisory-tier shape as `stopchecks/stopcheck_self_wired.py` (predicate-injection
# style: the pure functions below take their inputs as arguments, never reach for global state
# directly, so they're exercised with synthetic/tmp_path fixtures in tests without ever mutating
# the real live `checks/` package) -- but this check audits the checks/ catalog's own internal
# consistency, not whether the faculty is wired into the host at all.
#
# ADVISORY tier only (`level="advisory"`, never `"error"`), per this repo's "advisory over
# blocking" standing policy: a catalog-completeness drift is a maintenance signal, not a live
# integrity violation of anything the agent claimed this turn, so it must never block a turn.
from pathlib import Path

from makoto.substrate._declared import DECLARED_IDS
from makoto.registry import Check, discover, scan
from makoto.registry import POSTURE_ADVISE


def orphan_modules(*, package_dir: Optional[Path] = None) -> list[str]:
    """File stems present in checks/ that do NOT produce a `load_checks()`-discoverable CHECK:
    exists on disk, not discoverable/registered. Sorted for determinism."""
    return sorted(stem for stem, chk in scan(package_dir=package_dir).items() if chk is None)


def orphan_ids(*, package_dir: Optional[Path] = None,
               declared: Optional[dict] = None) -> list[str]:
    """IDs listed in the declared-IDs manifest with no live module backing them: declared, no
    module. `declared` defaults to the real catalog's `_declared.DECLARED_IDS` (test-injectable
    so a test can plant a dangling ID without touching the real manifest). Sorted for
    determinism."""
    reg = DECLARED_IDS if declared is None else declared
    live_ids = {chk.id for chk in discover(package_dir=package_dir)}
    return sorted(pid for pid in reg if pid not in live_ids)


def undeclared_falsifiable_gate(*, package_dir: Optional[Path] = None,
                                declared: Optional[dict] = None) -> Optional[Finding]:
    """Fires iff the checks/ catalog has an orphan on either side (see `orphan_modules` /
    `orphan_ids`); `None` (no finding) on a fully consistent catalog. Fail-open by
    construction: both halves already fail-open internally (`scan` never raises)."""
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
        level="advisory",
        message="checks/ catalog completeness drift -- " + "; ".join(parts),
        retry_hint=("Fix the checks/ catalog: give every on-disk module a valid CHECK "
                    "(id/applies_at/posture), and either implement or remove every "
                    "declared-but-missing manifest entry in _declared.py."),
    )


# tests="SPEC": registered ONE_OFF -- this audits registry/loader completeness itself.
undeclared_CHECK = Check(
    id="gate.undeclared_falsifiable",
    applies_at="Stop",
    posture=POSTURE_ADVISE,
    tests="SPEC",
    run=lambda ctx=None: undeclared_falsifiable_gate(),
)

# ==============================================================================================
# verifierExitMasking
# ==============================================================================================
# content.verifier_exit_masking — verifier EXIT-CODE masking (a test/build/lint runner's failure hidden).
#
# Forcing a verifier's exit code to 0 — `pytest || true`, `go test ; true`, an unrestored
# `set +e` before a runner, a masking `||` branch (`pytest || echo skip`), a trailing pipe
# (`pytest | tail -5` without pipefail), an `if` wrapper with no failing branch, a `$?`
# captured but never returned, or a subshell/brace group around any of these — manufactures
# a green that survives real failures. A core honesty cheat (CLAUDE.md commandment 1: no
# `|| true` / `; true` / `set +e` to hide failures). An `||`/`if` branch that RE-RAISES the
# failure (`pytest || exit 1`, `if pytest; ... else exit 1; fi`, `... exit $rc`) is honest
# handling and never fires.
#
# SCOPED to exit-code masking ONLY. Stream redirection (`2>/dev/null` / `&>/dev/null`) is deliberately
# OUT of scope: it does NOT alter `$?` (`sys.exit(7) 2>/dev/null` still exits 7) — every runner in
# _LEAD_RUNNER_RX signals failure via a nonzero exit, so silencing stderr cannot turn a real failure
# into a green.
#
# FP-SAFE BY SHELL COMMAND POSITION: this check tokenizes the Bash command and only treats a runner,
# mask, or `set +e` as evidence when it is an executed command/operator, not prose in a comment,
# quoted string, or Markdown/code-fence payload. This is necessarily heuristic rather than a Bash
# interpreter: malformed shell, heredocs, `eval`, and dynamically-built commands can still be
# misclassified or missed.
#
# The runner must be the LEADING command of a statement (an actual invocation), NOT an argument — so
# `find / -name pytest || true` does NOT fire (find is the command).
# Legit masks on NON-runners (pip uninstall||true, rm -rf build || true) carry no leading runner ->
# never fire. The mask must be in the SAME statement as the runner. `python -m` / `poetry run` / `npx`
# / `pnpm exec|dlx` / `uv|pdm|hatch|pipenv run` launcher prefixes ARE handled (stripped to the delegated
# runner, FP-safe). The bare `<tool> test/check` fallback (unknown tool, no launcher) remains DEFERRED.
#
# TWO RUNNER TIERS WITH DIFFERENT POSTURES (2026-09-03). `_LEAD_RUNNER_RX` is a foreign-ecosystem
# vocabulary — pytest, go test, npm test — and was blind to this estate's OWN verifier shapes
# (`python3 -m unittest`, `python3 tools/render_checks.py`, `./gates.sh`), so masks on them passed
# unseen. Recognition is widened by `_is_local_runner_command`, but ONLY under ADVISE:
#
#   * BLOCK (`level="error"`, a PreToolUse deny) remains bound to `_LEAD_RUNNER_RX` alone. Widening
#     a blocking vocabulary is expensive — every added token can deny a call on a guess — so the
#     blocking tier is UNCHANGED.
#   * ADVISE (`level="advisory"`, allow + additionalContext) carries the wider tier. It rests on
#     FILE NAMING, which is a heuristic, and a heuristic must not deny.
#
# WHAT THE WIDE TIER STILL CANNOT DECIDE, stated so the miss is counted rather than invisible: a
# verifier whose name carries no verification word — `python3 eval/replay.py`, `./go`,
# `./bin/verify-everything` — is RESIDUE. It is neither blocked nor surfaced, and this check does
# not know it was a verifier. The wide tier is itself a closed list; the difference is that its
# residue costs a missing advisory, never a false block.
#
# Knight-Leveson: stdlib `re` and `functools.lru_cache` only, plus two L0 package leaves
# (`core._shell` for the tokenizer, `core._declaredverifiers` for the declaration tier). The
# only I/O anywhere near this check is that reader's one memoised `makoto.toml` probe; the
# detection itself still reads nothing but the command string it was handed.
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

# --- the SECOND, WIDER runner tier: this estate's own verifier shapes (ADVISE only) -----------
# _LEAD_RUNNER_RX above is a foreign-ecosystem vocabulary — pytest, go test, npm test, cargo,
# gradle. It is blind to how THIS repository actually verifies itself: `python3 -m pytest` is
# covered only by accident of the `-m` strip, while `python3 tools/render_checks.py --check`,
# `python3 eval/replay.py`, `python3 -m unittest`, and `./gates.sh` are not recognized at all.
# A mask on any of those is a real hidden failure that this check silently allowed.
#
# THE ASYMMETRY, stated because it is the whole design and it costs something:
#   * BLOCK (level="error") stays bound to _LEAD_RUNNER_RX alone. It is UNCHANGED by this
#     widening. A deny is expensive and irreversible-ish for the agent's turn, so it is only
#     ever spent on a token whose runner-hood is unambiguous.
#   * ADVISE (level="advisory") carries the wider tier. A `.py` script is not necessarily a
#     verifier and a `.sh` script named `check-something` may be a deploy step; the wider tier
#     is a HEURISTIC over file naming, and a heuristic must not deny. It allows the call and
#     injects context naming the mask.
# The price paid deliberately: a genuinely masked `./gates.sh || true` is now SURFACED but NOT
# STOPPED. Recognition without a block is worth more than no recognition; a block on this
# evidence would be worth less than nothing.
#
# THIS TIER IS ALSO A CLOSED LIST, and says so. Its residue — an unlisted local verifier — costs
# an ADVISORY that never appears, never a false block. That is why widening here is affordable
# and widening _LEAD_RUNNER_RX would not be.
#
# --- the THIRD tier: RECOGNITION BY DECLARATION (blocking) ------------------------------------
# Both tiers above read NAMES, and a name is not an interface: the narrow one cannot see
# `python3 eval/replay.py` (this repository's own corpus replay) and the wide one matches
# `check-deploy.sh`, which may be a deploy step. `makoto.core._declaredverifiers` asks the
# repository instead — a `makoto.toml` at the event's `cwd` listing the programs it verifies
# itself with. That is a statement by the only party that knows, not a guess about spelling, so
# it is unambiguous in the sense `_is_runner_command` demands and may spend a deny.
# It is consulted BEFORE the naming heuristic and can only ADD a tier: a declaration cannot turn
# the heuristic off, because a declaration that could suppress findings would be a self-mute
# lever an agent pulls by declaring one harmless program (see checks/selfMuteGuard.py). Absent
# the file, every behaviour below is byte-for-byte what it was.
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
    """The statement's tokens from its LEADING command onward, after stripping leading `VAR=`
    assignments, `_WRAPPERS`, and ONE launcher prefix that delegates to a real runner
    (`python -m X`, `npx X`, `poetry|uv|pdm|hatch|pipenv run X`, `pnpm exec|dlx X`).

    Extracted so ALL THREE runner tiers normalize identically: the narrow blocking tier
    (`_is_runner_command`), the declaration tier (`_declares_this_verifier`) and the wide advisory
    tier (`_is_local_runner_command`) must agree on which token is "leading", or
    `sudo ./gates.sh || true` would be read one way by one tier and another by the next.

    MEMOISED, and returning a TUPLE so the shared value cannot be mutated by one caller under
    another. Each tier asks about the SAME statement text, so the tokenising pass is O(n) in the
    statement once and O(1) for every tier that repeats the question -- which also halves what
    the two pre-existing tiers were already paying. Bounded at 256 statements; the dispatcher
    forks per event, so the cache lives exactly as long as one hook invocation."""
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
    """True iff the statement's LEADING command (after VAR= / wrappers / launcher prefixes) is a verifier.

    THE BLOCKING TIER, deliberately NARROW and UNCHANGED by the 2026-09-03 widening: only
    `_LEAD_RUNNER_RX`'s explicit foreign-ecosystem runner names. A deny is only ever spent here.

    Launcher prefixes that DELEGATE to a runner are stripped so the runner becomes leading:
    `python -m pytest`, `poetry run pytest`, `npx eslint`, `pnpm exec jest`, `uv|pdm|hatch|pipenv run <runner>`.
    FP-SAFE: `python -m pip install` / `poetry run python app.py` keep a NON-runner leading -> never fire.
    """
    return bool(_LEAD_RUNNER_RX.match(" ".join(_leading_tokens(c))))


def _declares_this_verifier(lead_text: str, root) -> bool:
    """True iff this statement's leading program is one `root`'s `makoto.toml` declares.

    Normalises with the SAME `_leading_tokens` both other tiers use, so `sudo ./gates.sh` and
    `python3 gates.py` are read identically by all three — a tier that disagreed about which
    token leads would attribute one statement's mask to another statement's program.

    Callers gate this on `declares_anything(root)` BEFORE the statement loop, so a repository
    with no declaration never reaches the tokenisation below at all.
    """
    if not lead_text or not root:
        return False
    toks = _leading_tokens(lead_text)
    if not toks:
        return False
    # `python3 eval/replay.py`: the interpreter is not the verifier, the script is. Mirrors
    # `_is_local_runner_command`'s own interpreter walk, over declared names instead of a regex.
    if _PYTHON_RX.fullmatch(_basename(toks[0])) or _basename(toks[0]) in ("bash", "sh", "zsh"):
        for arg in toks[1:]:
            if arg.startswith("-"):
                continue
            return is_declared_verifier(arg, root)
    return is_declared_verifier(toks[0], root)


def _is_local_runner_command(c: str) -> bool:
    """True iff the leading command is one of THIS ESTATE's verifier shapes that
    `_LEAD_RUNNER_RX` cannot see. THE ADVISORY TIER — never a block. See the asymmetry note at
    `_LOCAL_SCRIPT_VERIFIER_RX`.

    Recognized: `python -m unittest|nose2|tox|nox|coverage|...` (the module runners), and a
    directly-executed script whose FILE NAME carries a verification word
    (`./gates.sh`, `python3 tools/render_checks.py`, `bash ci-check.sh`, `./run_tests.py`).

    WHAT THIS CANNOT DECIDE, named so the miss is counted rather than invisible:
      * A verifier whose file name says nothing — `python3 eval/replay.py`, `./go`, `make all`,
        `./bin/verify-everything` (no extension). Recognition rests on NAMING, and a script is
        under no obligation to be named honestly. These are RESIDUE: no advisory is emitted, and
        nothing is blocked. The gate does not know they were verifiers.
      * Whether a matched name IS a verifier. `check-deploy.sh` matches and may well be a deploy
        step. This is exactly why the tier is advisory: the false-positive cost is one line of
        injected context, not a denied call.
    Neither direction of this ambiguity may reach `level="error"`.
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

    `_shell_segments` appends segments re-parsed out of quoted `bash -c`/`sh -c`/`ssh`
    payloads AFTER all top-level segments, so pairing a runner with `segments[idx + 1]`
    across that boundary attributes another shell's `; true` to a top-level runner — a DENY
    resting on a false fact. This re-derives the boundary with the segmenter's own rule."""
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

    `(` is not a shlex punctuation char, so `(pytest` / `true)` arrive glued, and `{` / `}`
    arrive as standalone word tokens; either defeats both runner recognition and mask-literal
    matching. Group delimiters never change which command's exit survives, so they are
    stripped, and a delimiter-only segment donates its operator to the group it closed
    (`{ pytest; } || true` -> `pytest || true`). A `\\n` separator sequences exactly as `;`
    does and is normalized to it."""
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
    Combined flag groups count: `set +eu` disables errexit exactly as `set +e` does."""
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
    """True when any later same-scope segment re-raises the failure an operator swallowed:
    `exit`/`return` with a non-`0` argument (`exit 1`, `exit $rc`), bare `exit`/`return`
    (which propagate `$?`), or `false`. This separates `pytest || exit 1` and
    `if pytest; ... else exit 1; fi` (honest) from `pytest || echo skip` (masked)."""
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
    # The repository root the host reported, for the declaration tier. Read once here rather
    # than per segment; a payload without it simply declares nothing.
    declared_root = current_event.get("cwd") or ""
    # ONE memoised probe for the whole invocation. Without it the tier would ask per shell
    # statement, and a twelve-segment pipeline would pay twelve lookups to learn the same fact.
    declares = declares_anything(declared_root)
    segments = _normalized_segments(raw)

    reason = None
    # Which TIER supplied the runner for the fired `reason`. "block" = _LEAD_RUNNER_RX (the
    # narrow, unambiguous vocabulary); "advise" = _is_local_runner_command (the wide, naming-
    # heuristic estate tier). This variable is the whole asymmetry: it decides the Finding's
    # level and nothing else, and it can only ever SOFTEN — a lead-runner match always wins.
    tier = None
    # Errexit/pipefail state is tracked POSITIONALLY and PER SCOPE (top-level statements vs
    # segments re-parsed out of nested shell payloads): `set +e` masks only a runner that
    # executes AFTER it, in the SAME shell, with no restoring `set -e` in between. Anything
    # broader was measured producing DENYs on false facts (mask after the runner, mask
    # restored before it, mask inside a different shell's quoted payload).
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
        # The runner's scope ends where the top-level/nested flag flips (top-level segments
        # all precede nested ones); a mask is only evidence INSIDE that scope.
        end = idx + 1
        while end < len(segments) and segments[end][2] == is_top:
            end += 1
        next_argv = segments[idx + 1][0] if idx + 1 < end else []
        rest = [a for a, _op, _t in segments[idx + 1:end]]

        if operator in ("||", ";") and _is_exit_zero_literal(next_argv):
            # Either shape forces the statement's exit to 0 regardless of the runner's.
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
        # The asymmetry lands here and NOWHERE else. `level="error"` is the Pre-tier BLOCK wire
        # (dispatch._OUTCOME_FOR_LEVEL -> verdict.BLOCK -> permissionDecision "deny").
        # `level="advisory"` is verdict.ADVISE, which at the Pre edge ALLOWS the call and injects
        # the message as additionalContext. A widened-recognition hit is surfaced, never denied.
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

# ==============================================================================================
# undischargedWaiver
# ==============================================================================================
# makoto.checks.undischargedWaiver -- gate.undischarged_waiver, register entry
# `B9 WAIVER NEVER EXPIRES (+B25)`.
#
# The session introduced a directive that silences a checker, and nothing on or beside it says
# when the silence ends. The register states the rule as *"every waiver names a checkable
# discharge"* against the fault *"an exemption with no checkable end"*. A waiver with a rationale
# but no end is not a carve-out; it is a permanent hole with a sentence attached, and the sentence
# is why nobody revisits it.
#
# WHY MAKOTO'S MAP SAID NOT-COUNTABLE, AND WHAT THAT GOT RIGHT. The row read "an exemption's
# discharge is not a channel makoto reads", and that is true of the DISCHARGE ITSELF: makoto cannot
# tell whether issue #123 closed, whether the date passed, or whether the upstream bug was fixed.
# It never needed to. The register's rule is not "the waiver is discharged", it is "the waiver NAMES
# a checkable discharge" -- a property of the waiver's own text, and introduced text is a channel
# makoto already reads (`kit.introduced_text`, the same one every content precheck uses). The old
# verdict answered the harder question nobody asked.
#
# THE PRINCIPLE, WHICH IS ALSO THE NARROWING: a waiver fires only when NOTHING -- neither the
# instrument nor the text -- can say when it ends. Three forms are therefore excluded by design,
# because the instrument itself discharges them:
#
#   * `@ts-expect-error` -- the compiler errors when the suppressed error disappears.
#   * `@pytest.mark.xfail` -- the runner reports an XPASS when the test starts passing.
#   * `@pytest.mark.skipif(<cond>)` -- the condition is re-evaluated on every run.
#
# Their undischargeable counterparts (the bare ignore comment, the bare skip mark) do fire. That
# asymmetry is the whole check: it is not a lexicon of "bad words", it is the difference between a
# waiver that ends on its own and one that cannot.
#
# WHAT COUNTS AS NAMING AN END (`_DISCHARGE_RX`, read over the directive's own line and the line
# directly above it -- where a rationale conventionally sits): a tracked item (`#123`, `GH-7`,
# `ADR-42`, a `PROJ-123` key), a date or month (`2026-10-01`, `2026-10`), or an explicit temporal
# clause (`until ...`, `once ...`, `pending ...`, `remove when ...`, `expires ...`). Scope is one
# line above and the directive's own line, NOT the whole content: `checks/integritySuppressionFlag.py`
# already measured whole-content scope as a laundering token -- one unrelated `ADR-0` anywhere in the
# payload disarmed that check silently.
#
# RECALL BOUNDS, named rather than hidden:
#   * The discharge vocabulary is deliberately GENEROUS, because a miss here is a silent gate and a
#     miss there is noise. A character-set name shaped like a tracked-item key satisfies the
#     `PROJ-123` branch, so a directive whose trailing comment happens to mention one reads as
#     discharged. That is the accepted direction of the error.
#   * Only Write/Edit/MultiEdit/NotebookEdit are read. A waiver written through `sed -i` or a
#     heredoc is not seen. Bash was tried and REFUSED: `introduced_text` hands back the command
#     verbatim, so a grep FOR a commented lint directive carries a comment opener and the keyword
#     on one line and would be advised as an introduction. A false advisory on looking for waivers
#     is worse than missing one written through a stream editor. Measured, not supposed: with Bash
#     included, such a grep is reported.
#   * PostToolUse rows only. A PreToolUse row is a call that may never have landed, and a waiver
#     that was denied introduced nothing.
#
# MAKOTO'S OWN SUITE IS STRICTER THAN THIS GATE, not softer: `tests/_skipGuard.py` refuses a skipped
# test outright, so a bare skip cannot reach this tree at all. The gate advises on the agent's
# introduced waivers in whatever repository it is working in, which is a different subject.
#
# SELF-REFERENCE, AND WHY THE ANCHOR IS THE ANSWER. A check that spells its own trigger words is
# this ecosystem's standing lesson (scour refused to run on its own tree over a literal
# `scour-allow` in a test). The comment-opener anchor settles it structurally rather than by an
# exemption marker: a directive matches only when a comment opener precedes it ON THE SAME LINE, so
# the bare keywords below -- laid out one per line inside a verbose pattern -- do not match this
# module's own source. No `makoto-allow:` path exists here and none is wanted: a Stop-tier
# `GateContext` carries no `conn`, so an exemption could not be recorded, and an exemption that
# leaves no audit row is the laundering token this package refuses everywhere else. That is
# `B34 LAW EXEMPTS ITS INSTRUMENT` answered by construction instead of by a carve-out.
#
# ADVISORY TIER, NEVER BLOCK: a deliberately permanent waiver is a real and common thing -- a
# vendored file's lint exclusion, a directive on a shape the checker genuinely gets wrong -- and it
# looks identical here. No corpus-measured false-positive rate exists, so this gate advises.
from makoto.kit import decode_history_event, introduced_text

# Only the tools that carry introduced FILE content. Bash is deliberately absent -- see the
# docstring's recall bounds for the measurement that refused it.
_MUTATION_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})

# A checker-silencing directive, COMMENT-ANCHORED: a comment opener, then the keyword, on one
# line. The anchor is what makes this module immune to its own vocabulary (docstring, last
# section) and what keeps a keyword inside a string literal or an identifier from matching.
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
# trailing `\b` on its own (the `i` is a word character), and `xfail` is absent by design.
_BARE_SKIP_RX = re.compile(r"(?m)^[ \t]*@(?:pytest\.mark\.)?skip\b")

# An end a reader can go and check. Generous on purpose; the direction of the error is stated in
# the docstring's recall bounds.
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
# content -- checks/integritySuppressionFlag.py measured that scope as a laundering token.
_LOOKBACK = 1
# How many offenders the one finding NAMES. A presentation bound, not a detection one: every
# offender is counted, and `+N more` carries the rest. Set here because this is the only layer
# that renders -- checks/relativePathCitation.py makes the same call at 5 for the same reason.
_NAMED = 3


def _undischarged_directives(content: str) -> list:
    """Every silencing directive in `content` whose window names no checkable end.

    Returns `[(line_no, line_text), ...]`, one per offending line, deduplicated by line so a
    line carrying two directives is one offence.
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


def undischarged_waiver_gate(history) -> Optional[Finding]:
    """Fire iff a settled file mutation this session introduced a silencing directive with no
    checkable end named on or above it. One finding for the whole turn, naming the offenders."""
    hits = []
    for row in history or ():
        ev = decode_history_event(row)
        if not isinstance(ev, dict):
            continue                      # fail open: an undecodable row is no evidence
        if ev.get("hook_event_name") != "PostToolUse":
            continue                      # a call that may never have landed introduced nothing
        tool = ev.get("tool_name", "")
        if tool not in _MUTATION_TOOLS:
            continue
        ti = ev.get("tool_input", {}) or {}
        fp = ti.get("file_path", "") if isinstance(ti, dict) else ""
        for _, text in _undischarged_directives(introduced_text(tool, ti)):
            hits.append((fp, text))
    if not hits:
        return None
    named = "; ".join(f"`{t}`" + (f" in {f}" if f else "") for f, t in hits[:_NAMED])
    more = f" (+{len(hits) - _NAMED} more)" if len(hits) > _NAMED else ""
    return Finding(
        pattern_id="gate.undischarged_waiver",
        file=hits[0][0],
        line=0,
        level="advisory",
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


waiver_CHECK = _Check(id="gate.undischarged_waiver", applies_at="Stop", posture="ADVISE",
               may_block=True,
               tests="SPEC",
               eats=frozenset({"history"}),
               run=lambda c: undischarged_waiver_gate(c.history))

# ==============================================================================================
# relativePathCitation
# ==============================================================================================
# makoto.checks.relativePathCitation -- flags a chat response that cites a file path in a
# non-absolute (unclickable) form.
#
# Owner-reported pain: "the paths I keep complaining I cannot read -- when a link to read has a
# non-absolute path it's an unclickable link". Most terminal/IDE hosts only turn an ABSOLUTE path
# (or an explicit `file_path:line_number` citation, per this assistant's own house style) into a
# clickable jump target; a relative path ("checks/hollowTest.py:146") or a `~`-relative one
# ("~/.claude/foo.py") renders as plain, unclickable text in many hosts.
#
# ADVISORY tier only (never blocks): this is a communication-quality signal, not an integrity
# violation -- the same "advisory over blocking" standing policy `selfWiredCheck.py`/
# `staleEstablisher.py` already follow.
#
# Detection is DELIBERATELY narrow and syntactic (never a judgment call about whether a path is
# "important enough" to cite absolutely):
#   - A candidate token needs real path shape: either a directory separator ('/') plus a
#     dotted-extension basename, or a bare `name.ext:NNN` line-citation (this assistant's own
#     documented convention: "include the pattern file_path:line_number").
#   - Already-absolute ('/...') tokens are not flagged -- they ARE clickable.
#   - A token inside a fenced code block (```...```) is code being shown, not a citation being
#     made, so it is excluded (same fence-parity discipline `substrate/claims.py` uses).
#   - A token immediately preceded by a URL scheme (http://, https://, ftp://) is excluded -- a URL
#     path segment is not a filesystem citation.
#   - A dotted CODE IDENTIFIER (`Finding.source_event_id`, `obj.method`) or a version/pattern id
#     ("v1.2", "1.4.1") is excluded by requiring the post-dot segment to be a plausible lowercase
#     file extension, never purely digits and never capitalized (same firewall
#     `checks/silentlyDroppedCommitment.py`'s own location sourcer uses for exactly this false-positive
#     class).
from bisect import bisect_right


# A plausible file EXTENSION: short, lowercase, alphanumeric, not purely numeric -- the same
# firewall checks/silentlyDroppedCommitment.py uses to separate a real filename from a
# dotted code identifier or a version/pattern id.
_EXT_RX = r"[a-z][a-z0-9]{0,4}"
# A directory-qualified path: at least one '<segment>/' before a dotted basename. NOTE the two
# alternatives are not symmetric: the `~/` branch admits only a dotted basename DIRECTLY under the
# home root ('~/foo.py'), because no '<segment>/' repetition follows it -- '~/.claude/foo.py' is
# not matched today, and the leading-'/' lookbehind blocks re-entry at the inner '.claude/foo.py'.
_DIR_QUALIFIED_RX = re.compile(
    rf"(?<![\w/.~-])((?:~/|(?:[\w.-]+/)+)[\w.-]*\.{_EXT_RX}(?::\d+)?)(?![\w/])"
)
# A bare `name.ext:NNN` line-citation with no directory at all -- this assistant's own
# documented "file_path:line_number" convention, minus the directory qualifier. Still a citation
# (it names a specific line), still unclickable without an absolute root.
_BARE_CITATION_RX = re.compile(
    rf"(?<![\w/.~-])([\w-]+\.{_EXT_RX}:\d+)(?![\w/])"
)
_URL_SCHEME_RX = re.compile(r"(?:https?|ftp)://[\w.\-/]*$")
_FENCE_RX = re.compile(r"(?m)^\s{0,3}```")


def _in_fence(fence_ends: list, offset: int) -> bool:
    """True iff `offset` sits inside a ```fenced code block``` -- an ODD count of ``` fences
    before it means so (same parity trick `state/plan.py::source_plan_item_promise` uses).
    Identical to `len(_FENCE_RX.findall(text[:offset])) % 2 == 1`: a marker is counted by that
    prefix scan exactly when it ends at or before `offset`, i.e. when it fits wholly inside the
    prefix, which is what `bisect_right` over the marker END offsets counts."""
    return bisect_right(fence_ends, offset) % 2 == 1


def _after_url_scheme(text: str, start: int) -> bool:
    """True iff the text immediately before `start` ends in a URL scheme -- a URL path segment
    is not a filesystem citation."""
    return bool(_URL_SCHEME_RX.search(text[max(0, start - 32):start]))


def find_relative_citations(text: str) -> list[tuple[str, int]]:
    """Return [(path, offset), ...] for every non-absolute, non-URL, non-fenced path-shaped
    citation in `text`, in order of first appearance, each path reported once."""
    if not text:
        return []
    # End offset of every ``` fence marker, ascending -- scanned ONCE per call so the parity test
    # in `_in_fence` is a bisect, not a fresh whole-prefix scan per candidate (that form was
    # quadratic: a long turn citing many paths re-scanned the text once per citation). Inlined
    # rather than extracted: tests/test_gate_shape.py pins this module's top-level def count.
    fence_ends = [m.end() for m in _FENCE_RX.finditer(text)]
    seen = set()
    out = []
    for rx in (_DIR_QUALIFIED_RX, _BARE_CITATION_RX):
        for m in rx.finditer(text):
            path = m.group(1)
            # Belt-and-braces: the absolute-path and URL guards are ALREADY implied by the two
            # patterns' shared `(?<![\w/.~-])` lookbehind -- no match can begin with '/', and none
            # can begin right after the '/' or host chars a URL prefix ends in -- so neither can
            # fire as written. Both are kept as the explicit statement of intent that survives a
            # future loosening of that lookbehind. The fence guard is the live one.
            if path.startswith("/"):
                continue                              # already absolute -> clickable, not flagged
            if _in_fence(fence_ends, m.start()):
                continue                              # code being shown, not a citation
            if _after_url_scheme(text, m.start()):
                continue                              # a URL path segment, not a filesystem path
            if path in seen:
                continue
            seen.add(path)
            out.append((path, m.start()))
    out.sort(key=lambda t: t[1])
    return out


def relative_path_gate(text: str) -> Optional[Finding]:
    """Fire iff `text` (the assistant's own turn) cites at least one non-absolute path-shaped
    location. Names every distinct offender so a single response with several unclickable
    citations gets one finding, not one per occurrence."""
    hits = find_relative_citations(text)
    if not hits:
        return None
    names = ", ".join(f"`{p}`" for p, _ in hits[:5])
    more = f" (+{len(hits) - 5} more)" if len(hits) > 5 else ""
    return Finding(
        pattern_id="gate.relative_path_citation",
        file="",
        line=0,
        level="advisory",
        message=(
            f"cited path(s) not absolute, so not clickable in most hosts: {names}{more}. "
            f"Prefer an absolute path (or this assistant's own file_path:line_number convention "
            f"rooted at an absolute file_path)."
        ),
        retry_hint="Re-cite with an absolute path when referencing a specific file/location.",
    )


# `may_block=True` alongside posture="ADVISE" is the same structural-eligibility-only declaration
# selfWiredCheck.py carries: dispatch._blocking_gate_ids() keys off may_block alone, so the finding
# does reach _emit_decision -- where it folds to verdict.ADVISE, and the Stop/SubagentStop wire
# table has no ADVISE entry, so it renders {} and never denies. The never-blocks guarantee rests on
# posture=="ADVISE" plus level="advisory", not on this flag (pinned by
# tests/test_dispatch.py::test_dispatch_relative_path_citation_gate_never_blocks_even_when_it_fires).
relpath_CHECK = _Check(id="gate.relative_path_citation", applies_at="Stop", posture="ADVISE",
               tests="SPEC",
               eats=frozenset({"text"}),
               may_block=True, run=lambda c: relative_path_gate(c.text))

# ==============================================================================================
# claudeIdentity
# ==============================================================================================
# makoto.checks.claudeIdentity -- gate.claude_identity, register entry
# `A13 SETTING CALLED INHERENT`.
#
# A commit is about to be stamped with an identity nobody chose: the container's git layer (an
# env var or a config file) names Claude at the anthropic.com noreply address, and a plain
# `git commit` takes that setting as if it were who is writing. content.illusory_authorship_trailer
# reads the text a call introduces, so it never sees this: the author field is written from the
# git layer, not from the command. Measured 2026-09-23 over 17 trees: 834 commits authored this
# way, 0 caught.
#
# The entry's fix is to name which layer set the value and where it changes, and that is a
# reading makoto can take before the write: `git var GIT_AUTHOR_IDENT` / `GIT_COMMITTER_IDENT`
# run with the command's own overrides (leading `VAR=`, `env -u`, `export`/`unset`, `git -c`,
# `-C`, `cd`, `--author=`) is what git itself will stamp.
#
# Two edges, one reading. Upstream: a commit-creating git command whose author or committer
# resolves to Claude is refused before it runs. Damage control: a `git push` whose outgoing
# commits (not on any remote-tracking ref) carry one is refused before anything leaves the
# machine, which catches commits made where the first edge never looked (a script, a hook-less
# session). Any git failure reads as no finding: this gate fails open.
import os
import subprocess

from makoto.core._shell import _shell_segments

# Claude at the anthropic.com noreply address, and claude[bot] at its users.noreply.github.com
# address, are the two forms on the trees. A human named Claude with their own address passes.
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

# ==============================================================================================
# canonFingerprints
# ==============================================================================================
# gate.canon_fingerprints -- SPEC-5 Task 9 (Makoto absorbs Assay): the BLOCK-tier half of the 17
# in-scope canon session fingerprints (of the original 27-fingerprint THE_CANON,
# REF-lever-graded-primitives/signalminer/grade_planted.py) ported onto Makoto's real Stop-gate
# observable surface. See makoto/substrate/_canonAtoms.py's module docstring for the full scope-cut
# (10 of 27 need unimplemented atoms, not ported) and porting-fidelity notes, and its BLOCK_IDS for
# the citation trail on exactly which 4 of the 17 are blocking-capable by construction.
#
# LOADER-SHAPE DECISION (deliberate divergence from the ticket's literal "ONE new file" framing,
# discovered while implementing, not a preference): the 17 in-scope fingerprints split BLOCK/ADVISE,
# but tests/test_stop_gate_level_invariant.py enforces "one gate id -> one fixed Finding.level"
# ("error", unless the id is named in its advisory allowlist) -- a single mixed-posture module would
# violate that invariant the moment both tiers fired in the same turn. Resolution: TWO gate modules
# (this one, BLOCK-only; canonFingerprintsAdvisory.py, ADVISE-only), sharing their atom/decode logic
# via the package-plumbing file makoto/substrate/_canonAtoms.py (it sits in the substrate package,
# outside the `checks/*.py` glob registry's `_candidate_files` scans, and is underscore-prefixed on
# top of that -- not itself a detector). Both gate modules are flat files directly in checks/, so
# SPEC-5's "flat checks/, no sub-package" layout rule still holds.
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


fp_CHECK = _Check(id="gate.canon_fingerprints", applies_at="Stop", posture="BLOCK", may_block=True,
               tests="SPEC",
               eats=frozenset({"text", "history", "transcript_path", "session_id", "state_root"}),
               run=lambda c: canon_fingerprint_block_gate(
                   c.text, c.history, transcript_path=c.transcript_path,
                   session_id=c.session_id, state_root=c.state_root))

# ==============================================================================================
# canonFingerprintsAdvisory
# ==============================================================================================
# gate.canon_fingerprints_advisory -- SPEC-5 Task 9 (Makoto absorbs Assay): the ADVISE-tier half
# of the 17 in-scope canon session fingerprints (of the original 27-fingerprint THE_CANON,
# REF-lever-graded-primitives/signalminer/grade_planted.py) ported onto Makoto's real Stop-gate
# observable surface. See makoto/substrate/_canonAtoms.py's module docstring/BLOCK_IDS comment for the
# full scope-cut and posture-citation trail: these 13 either rest on a soft/claim atom the gold-oracle
# finding doc's robust core does not name, or are among the doc's explicitly-named WORST DISQUALIFIED
# fingerprints (nogreen_secret_testedit, red_no_green, claim_secret, claim_revert) -- so per SPEC-5's
# own total-retention rule they stay in the catalog, evaluated and recorded, but NEVER block.
#
# Sibling of canonFingerprints.py (the BLOCK-tier half); see that module's docstring for why this is
# two gate modules instead of one (tests/test_stop_gate_level_invariant.py's one-gate-id/one-fixed-
# level invariant). This id is named in makoto.registry's _ADVISORY_ALLOWLIST, the same mechanism
# gate.self_wired (FD6) already uses for its own advisory-only tier.


def canon_fingerprint_advisory_gate(text, history) -> List[Finding]:
    """One ADVISORY (never blocking) Finding per non-robust-core canon fingerprint that fires on
    this session's call stream. Silent (empty list) when none fire."""
    from makoto.substrate._canonAtoms import calls_from_history, fired_canon_fingerprints
    out: List[Finding] = []
    for name, formula, is_block in fired_canon_fingerprints(calls_from_history(history), text or ""):
        if is_block:
            continue
        out.append(Finding(
            pattern_id="gate.canon_fingerprints_advisory",
            file="", line=0, level="advisory",
            message=(f"canon.{name}: {formula} -- a gaming-shaped session fingerprint fired. "
                     "ADVISORY only: this fingerprint rests on a soft/claim atom or is among the "
                     "gold-oracle finding's named disqualified fingerprints, so it is recorded "
                     "but never blocks."),
            retry_hint="Advisory only -- review the flagged behavior; this never blocks a turn.",
        ))
    return out


fpadv_CHECK = _Check(id="gate.canon_fingerprints_advisory", applies_at="Stop", posture="ADVISE",
               tests="SPEC",
               eats=frozenset({"text", "history"}),
               may_block=True, run=lambda c: canon_fingerprint_advisory_gate(c.text, c.history))

# ==============================================================================================
# planItemDrift
# ==============================================================================================
# makoto.checks.planItemDrift -- ADVISORY reminder of open PLAN/TASK-LABELED commitments
# ("§9.3", "Task #19") a real session hit: a forward promise phrased as a section/task reference,
# never a file path, was silently dropped and never appeared in ANY commitment store because
# `gate.dropped`'s sourcer requires a file-shaped location and found none.
#
# `state/plan.py` sources/discharges these purely textually (no filesystem ground truth
# exists for a label); this check surfaces whatever is still open at Stop time as a reminder, ADVISORY
# tier ONLY -- unlike `gate.completion` (which blocks on a verifiable file-vs-filesystem contradiction),
# a label's "still open" state here is a weaker, textual-only signal with no corpus-measured FP rate
# yet, so it must never block (same "advisory over blocking" policy `selfWiredCheck.py`/
# `staleEstablisher.py` already follow, and the same caution the design review flagged for any
# chat-prose-sourced obligation).
# At most this many labels are named inline in the reminder; any remainder is counted, not named.
_LABEL_CAP = 8


def plan_item_drift_gate(open_items: list) -> Optional[Finding]:
    """Fire iff any plan-item commitment is still OPEN for this session -- a gentle, named
    reminder, never a block. `open_items=[]` (nothing open) is silent."""
    if not open_items:
        return None
    labels = ", ".join(i["label"] for i in open_items[:_LABEL_CAP])
    hidden = len(open_items) - _LABEL_CAP
    more = f" (+{hidden} more)" if hidden > 0 else ""
    return Finding(
        pattern_id="gate.plan_item_drift",
        file="",
        line=0,
        level="advisory",
        message=(
            f"plan/task-labeled commitment(s) still open: {labels}{more}. A textual-only signal "
            "(no filesystem ground truth for a label) -- confirm each is genuinely still pending, "
            "not silently dropped."
        ),
        retry_hint="Mark each done (a first-person past-tense statement naming it) or retract it explicitly.",
    )


drift_CHECK = _Check(id="gate.plan_item_drift", applies_at="Stop", posture="ADVISE",
               tests="SPEC",
               eats=frozenset({"open_plan_items"}),
               may_block=True, run=lambda c: plan_item_drift_gate(getattr(c, "open_plan_items", None) or []))

# ==============================================================================================
# phantomCitation
# ==============================================================================================
# content.phantom_citation predicate — phantom citation (Author-Year not in canonical set).
#
# Spec §5.6. Reads tool_input.content (NOT disk), extracts Author-Year strings
# via citations.extract_citations, queries the canonical_citations table via the
# dispatcher-passed conn. Fail-open if conn is None (Knight-Leveson: a missing
# DB must not block agent work).
from makoto.kit import _record_exemption, makoto_allow_reason, makoto_allowed, scan_target_content
from makoto.state.citations import extract_citations


citation__TARGET_RX = re.compile(r"\.md$")

def _canonical_path(conn) -> Optional[str]:
    """The configured canonical_citations_path, or None when unknown (missing config table/row)."""
    try:
        row = conn.execute("SELECT value FROM config WHERE key='canonical_citations_path'").fetchone()
    except Exception:
        return None   # no config table/row -> unknown
    if not row or not row[0]:
        return None
    return row[0]


def _governed_root(conn) -> Optional[Path]:
    """The project tree the loaded allowlist actually governs — the repo that owns the
    canonical_citations_path CITATIONS.md. The allowlist is project-specific (makoto's own cites),
    so it is only VALID to enforce for writes inside that tree; applied globally it false-fires on
    every legitimate Author-Year citation in any OTHER project. Returns None if the path is unknown
    (then we fall through to the prior global behavior rather than silently disabling the check)."""
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
# dispatcher entrypoint signature (a structural contract, not extractable logic), and the two
# bodies do unrelated things. Not to be "deduped".
def citation_predicate(*, current_event: dict, history: list, pattern: Check,
              conn=None) -> Optional[Finding]:
    """fire on first Author-Year string not present in canonical_citations."""
    if current_event.get("hook_event_name") != "PreToolUse":
        return None
    # `or {}`: the host may send `tool_input: null`; sibling checks (claimedShippedAbsent,
    # writeThrashRevert, ...) already no-op on it instead of raising into the dispatcher's
    # error row.
    tool_input = current_event.get("tool_input") or {}
    fp = tool_input.get("file_path", "")
    if not citation__TARGET_RX.search(fp) or fp.endswith("docs/CITATIONS.md"):
        return None
    if conn is None:
        # Fail-open: predicate requires DB; missing conn -> no decision.
        return None
    # Self-exemption by CONFIGURED path, not only the conventional docs/ suffix: an install whose
    # canonical file lives at <root>/CITATIONS.md must be able to edit its own allowlist — the
    # DENY otherwise tells the author to add the entry to the very file the write is adding it to.
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
    # The allowlist only validly governs its own project; a write outside that tree (another repo
    # that never adopted this CITATIONS.md) must not be judged against it, or every real citation
    # there false-fires now that makoto runs globally.
    if not _within_governed_tree(fp, current_event.get("cwd", ""), _governed_root(conn)):
        return None
    content = scan_target_content(tool_input)
    cites = extract_citations(content)
    if not cites:
        return None
    # An UNPOPULATED allowlist is indistinguishable from "every citation is phantom" only if we
    # let it deny: the same fail-open reasoning as `conn is None` applies (Knight-Leveson — a
    # missing/never-refreshed CITATIONS.md, e.g. moved after init so refresh_if_stale no-ops,
    # must not block agent work by denying every citation on a false fact).
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
        # DETECT-THEN-EXEMPT (R5b, matching kit._exempt_or_finding/introduced_regex_predicate):
        # the phantom is real, the marker suppresses the Finding, and the suppression is
        # RECORDED — the old order (exempt before detection) left no exemption row, so the
        # escape valve was invisible to review.
        _record_exemption(
            current_event, conn, pattern_id=pattern.id, file=fp, line=phantom[1],
            reason=makoto_allow_reason(content) or "", snippet=phantom[2].strip())
        return None  # AI documented these citations as legitimate (see CLAUDE.md)
    cite_str, line_no, snippet = phantom
    return Finding(
        pattern_id=pattern.id,
        file=fp,
        line=line_no,
        level="error",  # Pre-tier is invariantly BLOCK; Check has no fire_level (test_pre_tier_block_invariant.py)
        message=f"row {pattern.id} ({pattern.description}): '{cite_str}' not in canonical CITATIONS.md set",
        retry_hint=pattern.retry_hint,
        snippet=snippet,
    )


citation_RETRY_HINT = "Add the citation as an Author-Year entry to the canonical CITATIONS.md this install wired (the `canonical_citations_path` config row — the packaged makoto/docs/CITATIONS.md by default)."
citation_DESCRIPTION = 'phantom citation — Author-Year not in the canonical CITATIONS.md set'

# keywords: dispatch._keyword_hit is a case-sensitive raw-substring prefilter that GATES whether
# this predicate runs at all, so it must be a SUPERSET of what _CITATION_RX can match. Every
# citation carries a `\d{4}` year (any year — 'Ricardo 1817' is as phantom as 'Smith 2020', and
# the regex's `\s+` separator may be a newline, which json-escapes so ' 19'-style literals miss
# it); the only casing/escape-independent literal cover is "the payload contains a digit".
citation_CHECK = _Check(id='content.phantom_citation', applies_at="Pre", posture="BLOCK", predicate_module=__name__, keywords=tuple("0123456789"), retry_hint=citation_RETRY_HINT, description=citation_DESCRIPTION, eats=frozenset({"current_event", "pattern", "conn"}), tests="SPEC")



# gate.hollow_test / gate.liveness: Stop gates whose `run` is a stdlib-only AST analyzer kept in
# substrate (the detector-engine isolation law); each returns list[Finding].
# Imported when the row runs, not when the catalog loads: every PreToolUse call loads the catalog.
def hollow_run(ctx):
    from makoto.substrate.hollowTest import _run
    return _run(ctx)


def liveness_run(ctx):
    from makoto.substrate.deadPureStatement import _run
    return _run(ctx)


hollow_CHECK = _Check(id="gate.hollow_test", applies_at="Stop", posture="BLOCK", may_block=True, run=hollow_run,
               eats=frozenset({"touched", "cwd", "fs_read"}), tests="SPEC")
liveness_CHECK = _Check(id="gate.liveness", applies_at="Stop", posture="BLOCK", may_block=True, run=liveness_run,
               eats=frozenset({"touched", "cwd", "fs_read"}), tests="SPEC")

# ==============================================================================================
# the SPEC shape: its rows, and the one Pre entry dispatch calls for any of them
# ==============================================================================================
_ROWS = (env_CHECK, body_CHECK, weakened_CHECK, trailer_CHECK, suppress_CHECK, mute_CHECK, undeclared_CHECK, masking_CHECK, waiver_CHECK, relpath_CHECK, identity_CHECK, fp_CHECK, fpadv_CHECK, drift_CHECK, citation_CHECK, hollow_CHECK, liveness_CHECK,)
ROWS = {c.id: c for c in _ROWS}
CHECK, *EXTRA_CHECKS = _ROWS
_PREDICATES = {env_CHECK.id: env_predicate, body_CHECK.id: body_predicate, weakened_CHECK.id: weakened_predicate, trailer_CHECK.id: trailer_predicate, suppress_CHECK.id: suppress_predicate, mute_CHECK.id: mute_predicate, masking_CHECK.id: masking_predicate, identity_CHECK.id: identity_predicate, citation_CHECK.id: citation_predicate}


def predicate(*, current_event: dict, history: list, pattern, conn=None):
    """Dispatch calls one predicate per module; this shape's answers for the row it names."""
    return _PREDICATES[pattern.id](current_event=current_event, history=history, pattern=pattern, conn=conn)

