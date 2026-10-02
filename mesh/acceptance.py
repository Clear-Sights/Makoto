"""Inspect pytest acceptance references without importing product code."""
import ast
import shlex
from pathlib import Path


def references(root, selector, seen=None):
    seen = set() if seen is None else seen
    if selector in seen:
        return set()
    seen.add(selector)
    filename, *names = selector.split('::')
    path = root / filename
    tree = ast.parse(path.read_text())
    tests = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name.startswith('test_')]
    if names:
        tests = [n for n in tests if n.name == names[0]]
    if not tests:
        raise ValueError('empty or missing pytest target '+selector)
    found = {filename}
    for test in tests:
        for node in ast.walk(test):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == 'suite':
                    for arg in node.args:
                        if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
                            raise ValueError('uninspectable suite reference '+selector)
                        found.update(references(root, arg.value, seen))
                elif node.func.id.startswith('test_'):
                    found.update(references(root, filename+'::'+node.func.id, seen))
    return found


def errors(root, tasks):
    failures = []
    for task in tasks:
        try:
            targets = [word for word in shlex.split(task['check']) if word.startswith('tests/')]
            if not targets:
                raise ValueError('missing pytest target')
            needed = set().union(*(references(root, target) for target in targets))
            # zero measures completed fills; subtract uses the fixed checker.
            # Neither task writes acceptance tests.
            if task['task'] not in {'zero', 'subtract'}:
                outside = needed - set(task['inputs'].split(','))
                if outside:
                    raise ValueError('acceptance tests outside writable scope: '+','.join(sorted(outside)))
        except (OSError, SyntaxError, ValueError) as exc:
            failures.append(task['task']+': '+str(exc))
    return failures
