"""Rule d's lexical subjects and paired execution witnesses; never runs code.

File suffixes, shebangs, notebook protocol and declaration syntax classify edits.
Invocation positions classify executions, never words about claimed behavior.
Opaque/conditional calls need the host's actual makoto.invocation subject.
"""
import os
import json
import re
import shlex

from .borrowed import leaves
from .observed import FINAL, identity, git_action, text_of
from .precision import contains, names


CODE_SUFFIXES = frozenset('py pyw js jsx mjs cjs ts tsx sh bash zsh fish rb pl php lua r rs go c h cc cpp hpp java kt swift scala cs fs ex exs erl clj sql ps1 bat cmd ipynb'.split())
CONFIG_SUFFIXES = frozenset('json jsonc yaml yml toml ini cfg conf config xml properties env'.split())
CONFIG_FILES = frozenset(('Makefile', 'Dockerfile', 'Rakefile', 'Gemfile', 'Procfile', '.env'))
RUNTIMES = re.compile(r'(?:python(?:\d+(?:\.\d+)*)?|pypy\d*|node|nodejs|deno|bun|bash|sh|zsh|fish|ruby|perl|php|lua|Rscript|pwsh)\Z')
DECLARATIONS = re.compile(r'(?m)(?:\b(?:def|class|function|fn|func)\s+([A-Za-z_]\w*)|^\s*(?:export\s+)?(?:const\s+|let\s+|var\s+)?([A-Za-z_]\w*)\s*(?:=|:))')


def edited_forms(event, target):
    """Return code/config name forms for a recorded effect, or None for prose."""
    path = target.removeprefix('file:')
    suffix = os.path.splitext(path)[1].lstrip('.').lower()
    content = '\n'.join(value for _, value in leaves(event.get('tool_input', {})))
    payloads = [value for key, value in leaves(event.get('tool_input', {}))
                if key and key[-1] in ('content', 'new_string', 'old_string', 'new_source')]
    structured = False
    for value in payloads:
        try:
            structured |= isinstance(json.loads(value), (dict, list))
        except (ValueError, TypeError):
            pass
    if not (suffix in CODE_SUFFIXES | CONFIG_SUFFIXES
            or os.path.basename(path) in CONFIG_FILES
            or event.get('tool_name') == 'NotebookEdit'
            or re.search(r'(?m)^#!\s*\S+', content)
            or suffix not in ('md', 'rst', 'adoc') and (DECLARATIONS.search(content) or structured)):
        return None
    aliases = {s.text for s in names(content) if s.kind == 'identifier'}
    aliases.update(value for match in DECLARATIONS.finditer(content) for value in match.groups() if value)
    # JSON/YAML keys and dotted module names are also syntactic identifiers.
    aliases.update(re.findall(r'(?:^|[\n{,])\s*["\x27]([A-Za-z_]\w*)["\x27]\s*:', content))
    stem = os.path.splitext(os.path.basename(path))[0]
    if re.fullmatch(r'[A-Za-z_]\w*', stem):
        aliases.add(stem)
    absolute = identity(target, event)[5:]
    relative = os.path.relpath(absolute, event.get('cwd') or os.getcwd())
    module = os.path.splitext(relative)[0].replace(os.sep, '.')
    if re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', module):
        aliases.add(module.removesuffix('.__init__'))
    return {'subject': identity(target, event), 'display': target, 'aliases': aliases}


def names_change(event, change):
    """Every final/ship after code edits counts; writers require a literal name."""
    if event['hook_event_name'] in FINAL or event.get('tool_name') == 'Bash' and git_action(event):
        return True
    text = text_of(event)
    for span in names(text):
        path = re.sub(r':\d+(?::\d+)?$', '', span.text)
        if span.kind == 'path' and identity(path, event) == change['subject']:
            return True
    # Include space-containing paths in writer targets and quoted prose.
    ti = event.get('tool_input', {})
    if any(identity(ti[key], event) == change['subject'] for key in ('file_path', 'notebook_path') if ti.get(key)):
        return True
    absolute = change['subject'][5:]
    relative = os.path.relpath(absolute, event.get('cwd') or os.getcwd())
    return any(contains(text, value, 'path') for value in (absolute, relative, './' + relative)) or any(
        contains(text, alias, 'identifier') for alias in change['aliases'])


def simple_argv(command):
    """No guessed branch selection or shell expansion from an aggregate output."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=';&|()<>\n')
        lex.whitespace_split = True
        words = list(lex)
    except ValueError:
        return []
    if any(word and all(c in ';&|()<>\n' for c in word) for word in words):
        return []
    while words and (re.match(r'^[A-Za-z_]\w*=', words[0]) or words[0] in ('env', 'command', 'exec')):
        words = words[1:]
    # Substitution and globbing cannot identify an executed path deterministically.
    if any(any(c in word for c in '$*?`') for word in words):
        return []
    return words


def execution_subjects(pre, changes, post=None):
    """Subjects actually invoked by a simple native call or host observation.

    makoto.invocation.subject/subjects are host-owned actual execution targets,
    not arbitrary mentions in tool_input or assistant-produced receipts.
    """
    targets = []
    for event in (pre, post or {}):
        meta = event.get('makoto', {}).get('invocation', {})
        targets.extend(meta.get('subjects', []))
        if meta.get('subject'):
            targets.append(meta['subject'])
    tool, ti = pre.get('tool_name'), pre.get('tool_input', {})
    if tool in ('Run', 'Execute', 'NotebookExecute', 'NotebookRun'):
        targets.extend(ti[key] for key in ('file_path', 'notebook_path', 'script', 'path') if ti.get(key))
    elif tool == 'Bash':
        words = simple_argv(ti.get('command', ''))
        if words:
            program = os.path.basename(words[0])
            if RUNTIMES.fullmatch(program):
                args = words[1:]
                operand_flags = {'-W', '-X', '--require', '-r', '--loader', '--import', '--input-type', '--conditions', '--inspect-port'}
                i = 0
                while i < len(args):
                    arg = args[i]
                    if arg == '--':
                        i += 1
                        if i < len(args) and args[i] != '-':
                            targets.append(args[i])
                        break
                    if not arg.startswith('-'):
                        targets.append(arg)
                        break
                    # Only interpreter options, before the script/module operand,
                    # select eval/help/check mode; script arguments never do.
                    if arg == '-' or arg.startswith(('-c', '-e', '--eval', '--print')) or arg in ('-p', '--help', '-h', '--version', '-V', '--check'):
                        break
                    if program in ('bash', 'sh', 'zsh', 'fish') and (re.fullmatch(r'-[A-Za-z]*[cns][A-Za-z]*', arg) or arg == '--noexec'):
                        break
                    if program.startswith(('python', 'pypy')) and arg.startswith('-m'):
                        module = arg[2:] if arg != '-m' else args[i + 1] if i + 1 < len(args) else ''
                        if re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', module):
                            path = module.replace('.', '/')
                            candidates = [identity(path + ending, pre) for ending in ('.py', '/__main__.py')]
                            matches = [value for value in candidates if value in changes]
                            if len(matches) == 1:
                                targets.append(matches[0].removeprefix('file:'))
                            if module == 'pytest':
                                remaining = args[i + (1 if arg != '-m' else 2):]
                                targets.extend(w.split('::')[0] for w in remaining if not w.startswith('-'))
                        break
                    i += 2 if arg in operand_flags else 1
            elif program in ('.', 'source') and len(words) > 1:
                targets.append(words[1])
            elif program not in ('cat', 'head', 'tail', 'less', 'more', 'wc', 'rg', 'grep', 'ls', 'stat', 'find', 'echo', 'printf', 'touch', 'cp', 'mv', 'rm', 'sed', 'tee'):
                # Direct executables are a program position, never an argument.
                targets.append(words[0])
                if program in ('pytest', 'py.test'):
                    targets.extend(w.split('::')[0] for w in words[1:] if not w.startswith('-'))
                # Config consumption is explicit option syntax, not any mention.
                for i, word in enumerate(words[1:], 1):
                    if word == '--config' and i + 1 < len(words):
                        targets.append(words[i + 1])
                    elif word.startswith('--config='):
                        targets.append(word.split('=', 1)[1])
    return {identity(target, pre) for target in targets}


def run_output(post):
    """An error response counts; an absent response or launch receipt does not."""
    response = post.get('tool_response')
    if response is None:
        return False
    if isinstance(response, dict):
        if response.get('backgroundTaskId') or response.get('session_id') or response.get('sessionId') or response.get('running'):
            return any(isinstance(response.get(key), str) and bool(response[key])
                       for key in ('stdout', 'stderr', 'output'))
        # The host's returned status is a response even for a silent program.
        return any(key in response for key in ('stdout', 'stderr', 'output', 'content', 'exitCode', 'exit_code', 'exit'))
    return isinstance(response, (str, list))
