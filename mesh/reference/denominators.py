"""Preserved removed helpers, copied from their pre-subtraction definitions.

Reference only: the runtime never imports these four subsumed predicates.
"""
import ast
import json
import re


def cardinality(record, event):
    text = output_text(event)
    requirement = contract(record)
    if not re.search(r'(?i)\b(?:exactly|pin)\b', requirement):
        return []
    tree = tree_of(text)
    if tree is None:
        return []
    return [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Assert)
            and isinstance(n.test, ast.Compare) and any(isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for op in n.test.ops)
            and any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == 'len' for c in ast.walk(n.test))]


def direction(record, event):
    requirement = contract(record)
    lower = bool(re.search(r'(?i)\b(?:at least|minimum)\s+\d', requirement))
    upper = bool(re.search(r'(?i)\b(?:at most|maximum)\s+\d|smaller\s+\w+\s+are better', requirement))
    if lower == upper:
        return []
    tree = tree_of(output_text(event))
    if tree is None:
        return []
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assert) or not isinstance(n.test, ast.Compare) or len(n.test.ops) != 1:
            continue
        if not isinstance(n.test.comparators[0], ast.Constant) or not isinstance(n.test.comparators[0].value, (int, float)):
            continue
        op = n.test.ops[0]
        if (lower and isinstance(op, (ast.Lt, ast.LtE))) or (upper and isinstance(op, (ast.Gt, ast.GtE))):
            out.append(n.lineno)
    return out


def unknown_probe(record, event):
    try:
        value = json.loads(output_text(event))
    except (ValueError, TypeError):
        return []
    if not isinstance(value, dict) or value.get('present') is not False or value.get('evaluation') in ('unknown','not-evaluable'):
        return []
    probes = [o for o in record.obs if o.tool == 'Bash']
    if probes and probes[-1].exit not in (None, 0) and re.search(r'(?i)\bunknown\b|connection refused', probes[-1].output):
        return ['presence unknown']
    return []


def independent_evaluation(record, event):
    text = output_text(event)
    if not re.search(r'(?i)\bout.of.sample\b|\bindependent (?:accuracy|F1|evaluation|performance)\b', text):
        return []
    training = set()
    for o in record.obs:
        command = o.input.get('command', '') if o.tool == 'Bash' else ''
        training.update(re.findall(r'--train\s+([^\s]+)', command))
    evaluations = []
    for o in record.obs:
        command = o.input.get('command', '') if o.tool == 'Bash' else ''
        paths = re.findall(r'--data\s+([^\s]+)', command)
        if paths:
            evaluations.append((paths[-1], o))
    if not training or not evaluations:
        return []
    return ['training data reused'] if evaluations[-1][0] in training else []
