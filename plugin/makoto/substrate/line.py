"""One evaluator for the register's predicate lines: each claimed entry's set is one line in a fixed
language over what the hook sees, and this module is the only code that reads them. No model is
called anywhere here (Gabriel 2026-09-28 03:27Z: a model cannot judge itself); every term is a
script reading of one recorded event.

    line  := conj (" or " conj)*
    conj  := unary (" and " unary)*
    unary := "not " unary | "(" line ")" | seen(line) | unseen_since(line, line)
           | verifier | claim.names | claim.falsifier | tree.<ref>.exists | var op value
    op    := = != in matches >= <=
    value := "string" | {a,b} | NAME (a named set) | $var | number | word

A fact is a dict: event, tool, path, args{...}, settings{...}, exit, output, claim{kind, subject,
names, falsifier}, cwd. `var` names a field by dots; `$var` is the CURRENT event's value, also
inside seen(). seen(X): some earlier event satisfies X. unseen_since(X, Y): no event satisfies X
after the last one satisfying Y (the whole record when none does). verifier: this event's
command has exited nonzero at least once in the record. A `$name` that no fact carries raises
Unbound: the line is not evaluable, never silently false."""
from __future__ import annotations

import os
import re

_TOKEN = re.compile(r'\s*(?:(?P<str>"(?:\\.|[^"\\])*")|(?P<set>\{[^}]*\})|(?P<op>!=|>=|<=|=)'
                    r'|(?P<punct>[(),])|(?P<word>[^\s(),=!<>{}"]+))')
_OPS = ("=", "!=", "in", "matches", ">=", "<=")
_FLAGS = ("verifier", "claim.names", "claim.falsifier")


class Unbound(LookupError):
    """A `$name` the current event does not carry."""


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
        if kind == "word" and text in ("in", "matches"):
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
        node = ("and", [self.unary()])
        while self.peek()[1] == "and":
            self.take("and")
            node[1].append(self.unary())
        return node if len(node[1]) > 1 else node[1][0]

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
        if text in ("seen", "unseen_since") and self.peek(1)[1] == "(":
            self.take()
            self.take("(")
            first = self.line()
            if text == "seen":
                self.take(")")
                return ("seen", first)
            self.take(",")
            second = self.line()
            self.take(")")
            return ("unseen_since", first, second)
        if text in _FLAGS:
            self.take()
            return ("flag", text)
        if kind == "word" and text.startswith("tree.") and text.endswith(".exists"):
            self.take()
            return ("exists", self.value_of(text[len("tree."):-len(".exists")]))
        if kind != "word":
            raise Malformed(f"expected a variable, found {text!r}")
        self.take()
        op = self.take()
        if op[0] != "op" or op[1] not in _OPS:
            raise Malformed(f"expected an operator after {text}, found {op[1]!r}")
        vk, vt = self.take()
        return ("cmp", text, op[1], self.value(vk, vt))

    def value(self, kind, text):
        if kind == "str":
            return ("lit", re.sub(r'\\"', '"', text[1:-1]))
        if kind == "set":
            return ("set", frozenset(p.strip() for p in text[1:-1].split(",") if p.strip()))
        return self.value_of(text)

    def value_of(self, text):
        if text.startswith("$"):
            return ("ref", text[1:])
        if text.isupper() and not text.isdigit():
            if text not in self.named:
                raise Malformed(f"named set {text} has no table")
            return ("named", text)
        return ("lit", text)


def parse(line: str, named: dict | None = None):
    """The tree of one line; Malformed when it is outside the language."""
    p = _Parser(line, named or {})
    node = p.line()
    if p.peek()[0] is not None:
        raise Malformed(f"trailing {p.peek()[1]!r}")
    return node


def get(fact: dict, dotted: str):
    cur = fact
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _resolve(val, cur: dict, named: dict):
    kind, x = val
    if kind == "ref":
        got = get(cur, x)
        if got is None:
            raise Unbound(x)
        return ("value", got)       # a recorded value: compared as text, matched literally
    if kind == "named":
        return ("set", named[x])
    return val


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _cmp(have, op: str, val) -> bool:
    kind, want = val
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
    return a >= b if op == ">=" else a <= b


def evaluate(node, fact: dict, record: list, cur: dict | None = None, named: dict | None = None) -> bool:
    """Whether `fact` (an event) satisfies `node`, with `record` the earlier events (oldest first)
    and `cur` the current event that `$v` names (the fact itself at the top level)."""
    cur = fact if cur is None else cur
    named = named or {}
    op = node[0]
    if op == "or":
        return any(evaluate(n, fact, record, cur, named) for n in node[1])
    if op == "and":
        return all(evaluate(n, fact, record, cur, named) for n in node[1])
    if op == "not":
        return not evaluate(node[1], fact, record, cur, named)
    if op == "seen":
        return any(evaluate(node[1], e, record[:i], cur, named) for i, e in enumerate(record))
    if op == "unseen_since":
        last = max((i for i, e in enumerate(record) if evaluate(node[2], e, record[:i], cur, named)), default=-1)
        return not any(evaluate(node[1], e, record[:i], cur, named)
                       for i, e in enumerate(record) if i > last)
    if op == "flag":
        if node[1] == "verifier":
            cmd = get(fact, "args.command")
            return cmd is not None and any(get(e, "args.command") == cmd and e.get("exit") not in (0, None)
                                           for e in record + [fact])
        return bool(get(fact, node[1]))
    if op == "exists":
        _, where = _resolve(node[1], cur, named)
        base = fact.get("cwd") or cur.get("cwd") or "."
        return os.path.exists(os.path.join(base, str(where)))
    _, var, cmp_op, val = node
    return _cmp(get(fact, var), cmp_op, _resolve(val, cur, named))


def holds(line: str, fact: dict, record: list, named: dict | None = None) -> bool:
    return evaluate(parse(line, named), fact, record, named=named)


def canonical(line: str, named: dict | None = None) -> str:
    """The line with every conjunction and disjunction sorted: two entries whose lines are equal
    here are one entry."""
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
        if n[0] == "flag":
            return n[1]
        if n[0] == "exists":
            return f"tree.{_val(n[1])}.exists"
        return f"{n[1]}{n[2] if n[2] in ('=', '!=', '>=', '<=') else ' ' + n[2] + ' '}{_val(n[3])}"
    return show(parse(line, named))


def _val(v):
    kind, x = v
    if kind == "ref":
        return "$" + x
    if kind == "named":
        return x
    if kind == "set":
        return "{" + ",".join(sorted(x)) + "}"
    s = str(x)
    return s if re.fullmatch(r"[\w.\-/]+", s) else '"' + s.replace('"', '\\"') + '"'
