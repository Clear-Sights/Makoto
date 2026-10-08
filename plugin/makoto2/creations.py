"""Syntactic introductions in native writes, without treating them as readings."""
import ast
import ntpath
import re

from .observed import WRITERS
from .precision import contains, names
from .shell import ordered_segments


def introduces(ledger, event):
    if event.get('tool_name') not in WRITERS:
        return False
    ti = event.get('tool_input', {})
    text = '\n'.join(ti.get(k, '') for k in ('content', 'new_string', 'new_source'))
    target = ti.get('file_path') or ti.get('notebook_path')
    if not target or not text.strip():
        return False
    # Existing names and located references retain their independent holds.
    prior = ledger.given + [t for r in ledger.readings + ledger.inputs for t in r['texts']]
    for span in names(text):
        if span.kind in ('path', 'url', 'external-package') or any(contains(t, span.text, span.kind) for t in prior):
            return False
    try:
        tree = ast.parse(text)
        if any(isinstance(n, (ast.Assign, ast.AnnAssign, ast.FunctionDef, ast.ClassDef)) for n in tree.body):
            return True
    except SyntaxError:
        pass
    if re.fullmatch(r'(?:[A-Za-z_]\w*=[^\n]*\n?)+', text):
        return True
    if ntpath.splitext(target)[1] in ('.sh', '.bash', '.zsh'):
        return ordered_segments(text) is not None
    return False
