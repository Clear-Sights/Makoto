"""One evaluator for the register's predicate lines: each claimed entry's set is one line in a fixed
language over what the hook sees, and this module is the only code that reads them. No model is
called anywhere here (Gabriel 2026-09-28 03:27Z: a model cannot judge itself); every term is a
script reading of one recorded event.

    line  := conj (" or " conj)*
    conj  := unary (" and " unary)*
    unary := "not " unary | "(" line ")" | seen(line) | unseen_since(line, line)
           | exists NAME in set " and " conj            (the rest of the conjunction is the body)
           | count(line [, line]) op number             (events since the last reset that hold)
           | verifier | claim.names | claim.falsifier | tree.<ref>.exists
           | set op value | set                        (a bare set or field is its truth)
    set   := term ("-" term)*                          (difference of the keys or members)
    term  := var | fn(arg, ...)[.attr] | {a,b}
    op    := = != in matches contains >= <= > <
    value := "string" | {a,b} | NAME (a named set) | $var | number | word | var.with.dots | fn(...)

A fact is a dict: event, tool, path, args{...}, settings{...}, exit, output, claim{kind, subject,
names, falsifier}, cwd, source{read{path: hash}}. `var` names a field by dots and `[n]` by a name
`exists` bound; `tree[n].hash` is the file's hash now. `$var` is the CURRENT event's value, also
inside seen(). seen(X): some earlier event satisfies X. unseen_since(X, Y): no event satisfies X
after the last one satisfying Y (the whole record when none does). verifier: this event's
command has exited nonzero at least once in the record. A `$name`, a field or a function that no
fact carries raises Unbound: the line is not evaluable, never silently false."""
from __future__ import annotations

import hashlib
import os
import re

from makoto.vocab import _lazy_re

_TOKEN = _lazy_re(r'\s*(?:(?P<str>"(?:\\.|[^"\\])*")|(?P<set>\{[^}]*\})|(?P<op>!=|>=|<=|=|<|>)'
                  r'|(?P<punct>[(),])|(?P<word>[^\s(),=!<>{}"]+))')
_OPS = ("=", "!=", "in", "matches", "contains", ">=", "<=", ">", "<")
_FLAGS = ("verifier", "claim.names", "claim.falsifier")
_ENDS = (None, "and", "or", ")", ",")
_REFS_RX = _lazy_re(r"(?<![\w/.-])((?:\.{0,2}/)?[\w.-]+(?:/[\w.-]+)*\.[A-Za-z]\w{0,7})(?::\d+)?(?![\w/])")


class Unbound(LookupError):
    """A `$name`, field or function the facts do not carry."""


class Malformed(ValueError):
    """A line outside the language."""


def _tokens(line: str) -> list:
    out, i = [], 0
    while i < len(line):
        if line[i:].strip() == "":
            break
        m = _TOKEN.match(line, i)
        if not m or m.end() == i:
            raise Malformed(f"cannot read {line[i:i + 20]!r}")
        kind = m.lastgroup
        text = m.group(kind)
        if kind == "word" and text in ("in", "matches", "contains"):
            kind = "op"
        out.append((kind, text))
        i = m.end()
    return out


class _Parser:
    def __init__(self, line: str, named: dict):
        self.toks, self.i, self.named = _tokens(line), 0, named

    def peek(self, k=0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else (None, None)

    def take(self, text=None):
        tok = self.peek()
        if tok[0] is None or (text is not None and tok[1] != text):
            raise Malformed(f"expected {text or 'a term'}, found {tok[1]!r}")
        self.i += 1
        return tok

    def line(self):
        node = ("or", [self.conj()])
        while self.peek()[1] == "or":
            self.take("or")
            node[1].append(self.conj())
        return node if len(node[1]) > 1 else node[1][0]

    def conj(self):
        parts = []
        while True:
            if self.peek()[1] == "exists":
                parts.append(self.exists())
                break
            parts.append(self.unary())
            if self.peek()[1] != "and":
                break
            self.take("and")
        return ("and", parts) if len(parts) > 1 else parts[0]

    def exists(self):
        self.take("exists")
        kind, name = self.take()
        if kind != "word":
            raise Malformed(f"expected a name after exists, found {name!r}")
        op = self.take()
        if op[1] != "in":
            raise Malformed(f"expected in after exists {name}, found {op[1]!r}")
        over = self.setexpr()
        self.take("and")
        return ("exists", name, over, self.conj())

    def unary(self):
        kind, text = self.peek()
        if text == "not":
            self.take()
            return ("not", self.unary())
        if text == "(":
            self.take()
            node = self.line()
            self.take(")")
            return node
        if text in ("seen", "unseen_since", "count") and self.peek(1)[1] == "(":
            self.take()
            self.take("(")
            first = self.line()
            if text == "seen":
                self.take(")")
                return ("seen", first)
            if text == "count":
                reset = None
                if self.peek()[1] == ",":
                    self.take(",")
                    reset = self.line()
                self.take(")")
                op = self.take()
                if op[0] != "op" or op[1] not in (">=", "<=", ">", "<", "="):
                    raise Malformed(f"expected a comparison after count(...), found {op[1]!r}")
                vk, vt = self.take()
                return ("count", first, reset, op[1], self.value(vk, vt))
            self.take(",")
            second = self.line()
            self.take(")")
            return ("unseen_since", first, second)
        if text in _FLAGS and self.peek(1)[1] in _ENDS:
            self.take()
            return ("flag", text)
        if kind == "word" and text.startswith("tree.") and text.endswith(".exists"):
            self.take()
            return ("exists_path", self.value_of(text[len("tree."):-len(".exists")]))
        if kind not in ("word", "set"):
            raise Malformed(f"expected a variable, found {text!r}")
        left = self.setexpr()
        if self.peek()[1] in _ENDS:
            return ("truth", left)                       # a bare field, set or call: its truth
        op = self.take()
        if op[0] != "op" or op[1] not in _OPS:
            raise Malformed(f"expected an operator after {self.show(left)}, found {op[1]!r}")
        vk, vt = self.take()
        return ("cmp", left, op[1], self.value(vk, vt))

    def setexpr(self):
        node = self.term()
        while self.peek()[0] == "word" and self.peek()[1].startswith("-") and len(self.peek()[1]) > 1:
            _k, text = self.take()
            self.toks.insert(self.i, ("word", text[1:]))
            node = ("minus", node, self.term())
        return node

    def term(self):
        kind, text = self.take()
        if kind == "set":
            return ("lit", _set_of(text))
        if kind != "word":
            raise Malformed(f"expected a term, found {text!r}")
        if self.peek()[1] == "(":
            self.take("(")
            args, depth, cur = [], 0, []
            while True:
                k, t = self.take()
                if t == "(":
                    depth += 1
                elif t == ")" and depth == 0:
                    break
                elif t == ")":
                    depth -= 1
                if t == "," and depth == 0:
                    args.append("".join(cur))
                    cur = []
                else:
                    cur.append(t)
            if cur:
                args.append("".join(cur))
            attr = None
            if self.peek()[0] == "word" and self.peek()[1].startswith("."):
                attr = self.take()[1][1:]
            return ("call", text, tuple(args), attr)
        return ("var", text)

    @staticmethod
    def show(node):
        return node[1] if node[0] == "var" else node[0]

    def value(self, kind, text):
        if kind == "str":
            return ("lit", re.sub(r'\\"', '"', text[1:-1]))
        if kind == "set":
            return ("set", _set_of(text))
        if kind == "word" and self.peek()[1] == "(":
            self.i -= 1
            return ("term", self.term())
        return self.value_of(text)

    def value_of(self, text):
        if text.startswith("$"):
            return ("ref", text[1:])
        if text.isupper() and not text.isdigit():
            if text not in self.named:
                raise Malformed(f"named set {text} has no table")
            return ("named", text)
        if ("." in text or "[" in text) and _num(text) is None:
            return ("field", text)                     # another field of the same fact
        return ("lit", text)


def _set_of(text: str) -> frozenset:
    return frozenset(p.strip() for p in text[1:-1].split(",") if p.strip())


def parse(line: str, named: dict | None = None):
    """The tree of one line; Malformed when it is outside the language."""
    p = _Parser(line, named or {})
    node = p.line()
    if p.peek()[0] is not None:
        raise Malformed(f"trailing {p.peek()[1]!r}")
    return node


_PART_RX = _lazy_re(r"([^.\[\]]+)(?:\[([^\]]+)\])?")


def get(fact: dict, dotted: str, bind: dict | None = None):
    """The field `dotted` names: `a.b`, `a[n].b` with `n` bound by `exists`, and `tree[n].hash`,
    the hash of that file under the fact's cwd now. None when absent."""
    cur, bind = fact, bind or {}
    parts = _PART_RX.findall(dotted)
    if parts and parts[0][0] == "tree" and parts[0][1]:
        where = bind.get(parts[0][1], parts[0][1])
        path = os.path.join(fact.get("cwd") or ".", str(where))
        rest = [p for p, _ in parts[1:]]
        if rest != ["hash"]:
            return None
        return file_hash(path)
    for part, idx in parts:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
        if idx:
            key = bind.get(idx, idx)
            if not isinstance(cur, dict) or key not in cur:
                return None
            cur = cur[key]
    return cur


def file_hash(path: str):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except OSError:
        return None


def refs(text) -> frozenset:
    """The file paths a text names (`src/a.py`, `docs/X.md:12`): the lineage and drift lines' refs()."""
    return frozenset(m.group(1) for m in _REFS_RX.finditer(text if isinstance(text, str) else ""))


def _as_set(x) -> frozenset:
    if x is None:
        return frozenset()
    if isinstance(x, (dict, set, frozenset, list, tuple)):
        return frozenset(str(k) for k in x)
    return frozenset({str(x)})


_FUNCS = {"refs": lambda fact, arg, bind: refs(get(fact, arg, bind))}


def _term(node, fact, bind):
    kind = node[0]
    if kind == "lit":
        return node[1]
    if kind == "var":
        got = get(fact, node[1], bind)
        if got is None and "[" in node[1]:
            return None
        return got
    if kind == "minus":
        return _as_set(_term(node[1], fact, bind)) - _as_set(_term(node[2], fact, bind))
    if kind == "call":
        fn = _FUNCS.get(node[1])
        if fn is None or node[3] is not None or len(node[2]) != 1:
            raise Unbound(f"{node[1]}(...)")        # no fact carries it yet: not evaluable
        return fn(fact, node[2][0], bind)
    raise Malformed(f"not a term: {node!r}")


def _resolve(val, cur: dict, named: dict, fact: dict, bind: dict):
    kind, x = val
    if kind == "ref":
        got = get(cur, x, bind)
        if got is None:
            raise Unbound(x)
        return ("value", got)       # a recorded value: compared as text, matched literally
    if kind == "named":
        return ("set", named[x])
    if kind == "field":
        return ("value", get(fact, x, bind))
    if kind == "term":
        return ("value", _term(x, fact, bind))
    return val


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _cmp(have, op: str, val) -> bool:
    kind, want = val
    if isinstance(have, (dict, set, frozenset, list, tuple)) and op != "contains":
        mine = _as_set(have)
        if kind == "set" or isinstance(want, (set, frozenset, dict, list, tuple)):
            other = _as_set(want)
            return {"=": mine == other, "!=": mine != other, "in": mine <= other}.get(op, False)
        return {"=": mine == {str(want)}, "!=": mine != {str(want)}, "in": mine <= {str(want)}}.get(op, False)
    if op == "contains":
        if isinstance(want, (set, frozenset, list, tuple, dict)):
            return _as_set(want) <= _as_set(have) if have is not None else False
        return have is not None and str(want) in (_as_set(have) if not isinstance(have, str) else have)
    if have is None:
        return op == "!=" and want is not None
    many = kind == "set"
    if op == "=":
        return str(have) in want if many else str(have) == str(want)
    if op == "!=":
        return str(have) not in want if many else str(have) != str(want)
    if op == "in":
        return str(have) in (want if many else {str(want)})
    if op == "matches":
        pats = [re.escape(str(want))] if kind == "value" else [str(p) for p in (want if many else (want,))]
        return any(re.search(p, str(have)) for p in pats)
    a, b = _num(have), _num(want)
    if a is None or b is None:
        return False
    return {">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b}[op]


def evaluate(node, fact: dict, record: list, cur: dict | None = None, named: dict | None = None,
             bind: dict | None = None) -> bool:
    """Whether `fact` (an event) satisfies `node`, with `record` the earlier events (oldest first)
    and `cur` the current event that `$v` names (the fact itself at the top level)."""
    cur = fact if cur is None else cur
    named = named or {}
    bind = bind or {}
    op = node[0]
    if op == "or":
        return any(evaluate(n, fact, record, cur, named, bind) for n in node[1])
    if op == "and":
        return all(evaluate(n, fact, record, cur, named, bind) for n in node[1])
    if op == "not":
        return not evaluate(node[1], fact, record, cur, named, bind)
    if op == "seen":
        return any(evaluate(node[1], e, record[:i], cur, named, bind) for i, e in enumerate(record))
    if op == "unseen_since":
        last = max((i for i, e in enumerate(record) if evaluate(node[2], e, record[:i], cur, named, bind)),
                   default=-1)
        return not any(evaluate(node[1], e, record[:i], cur, named, bind)
                       for i, e in enumerate(record) if i > last)
    if op == "count":
        _, what, reset, cmp_op, val = node
        last = -1 if reset is None else max(
            (i for i, e in enumerate(record) if evaluate(reset, e, record[:i], cur, named, bind)), default=-1)
        n = sum(1 for i, e in enumerate(record) if i > last and evaluate(what, e, record[:i], cur, named, bind))
        return _cmp(n, cmp_op, _resolve(val, cur, named, fact, bind))
    if op == "exists":
        _, name, over, body = node
        return any(evaluate(body, fact, record, cur, named, {**bind, name: item})
                   for item in sorted(_as_set(_term(over, fact, bind))))
    if op == "flag":
        if node[1] == "verifier":
            cmd = get(fact, "args.command")
            return cmd is not None and any(get(e, "args.command") == cmd and e.get("exit") not in (0, None)
                                           for e in record + [fact])
        return bool(get(fact, node[1]))
    if op == "exists_path":
        _, where = _resolve(node[1], cur, named, fact, bind)
        base = fact.get("cwd") or cur.get("cwd") or "."
        return os.path.exists(os.path.join(base, str(where)))
    if op == "truth":
        return bool(_term(node[1], fact, bind))
    _, left, cmp_op, val = node
    return _cmp(_term(left, fact, bind), cmp_op, _resolve(val, cur, named, fact, bind))


def holds(line: str, fact: dict, record: list, named: dict | None = None) -> bool:
    return evaluate(parse(line, named), fact, record, named=named)


def canonical(line: str, named: dict | None = None) -> str:
    """The line with every conjunction and disjunction sorted: two entries whose lines are equal
    here are one entry."""
    def term(n):
        if n[0] == "var":
            return n[1]
        if n[0] == "lit":
            return "{" + ",".join(sorted(n[1])) + "}"
        if n[0] == "minus":
            return f"{term(n[1])}-{term(n[2])}"
        return f"{n[1]}({','.join(n[2])})" + (f".{n[3]}" if n[3] else "")

    def show(n):
        if n[0] in ("or", "and"):
            return f" {n[0]} ".join(sorted(("(" + show(c) + ")") if c[0] in ("or", "and") else show(c)
                                           for c in n[1]))
        if n[0] == "not":
            return "not " + (f"({show(n[1])})" if n[1][0] in ("or", "and") else show(n[1]))
        if n[0] == "seen":
            return f"seen({show(n[1])})"
        if n[0] == "unseen_since":
            return f"unseen_since({show(n[1])}, {show(n[2])})"
        if n[0] == "count":
            reset = f", {show(n[2])}" if n[2] is not None else ""
            return f"count({show(n[1])}{reset}){n[3]}{_val(n[4])}"
        if n[0] == "exists":
            return f"exists {n[1]} in {term(n[2])} and {show(n[3])}"
        if n[0] == "flag":
            return n[1]
        if n[0] == "exists_path":
            return f"tree.{_val(n[1])}.exists"
        if n[0] == "truth":
            return term(n[1])
        return f"{term(n[1])}{n[2] if n[2] in ('=', '!=', '>=', '<=', '>', '<') else ' ' + n[2] + ' '}{_val(n[3])}"
    return show(parse(line, named))


def _val(v):
    kind, x = v
    if kind == "ref":
        return "$" + x
    if kind in ("named", "field"):
        return x
    if kind == "term":
        return f"{x[1]}({','.join(x[2])})" + (f".{x[3]}" if x[3] else "")
    if kind == "set":
        return "{" + ",".join(sorted(x)) + "}"
    s = str(x)
    return s if re.fullmatch(r"[\w.\-/]+", s) else '"' + s.replace('"', '\\"') + '"'
