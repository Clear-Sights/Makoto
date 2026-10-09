"""Rule d's lexical subjects and paired execution witnesses; never runs code.

File suffixes, shebangs, notebook protocol and declaration syntax classify edits.
Invocation positions classify executions, never words about claimed behavior.
Opaque/conditional calls need the host's actual makoto.invocation subject.
"""
import os
import ntpath
import json
import re
import shlex
import ast

from .borrowed import leaves
from .observed import FINAL, identity, git_action, text_of
from .precision import contains, names
from .shell import redirected_argv
from .paths import relative_path, path_spellings, program_name


CODE_SUFFIXES = frozenset('py pyw js jsx mjs cjs ts tsx sh bash zsh fish rb pl php lua r rs go c h cc cpp hpp java kt swift scala cs fs ex exs erl clj sql ps1 bat cmd ipynb tcl awk'.split())
CONFIG_SUFFIXES = frozenset('json jsonc yaml yml toml ini cfg conf config xml properties env'.split())
RECORD_SUFFIXES = frozenset('md txt rst csv tsv jsonl ndjson log'.split())
DATA_SUFFIXES = CONFIG_SUFFIXES | RECORD_SUFFIXES
CONFIG_FILES = frozenset(('Makefile', 'Dockerfile', 'Rakefile', 'Gemfile', 'Procfile', '.env'))
RUNTIMES = re.compile(r'(?:python(?:\d+(?:\.\d+)*)?|pypy\d*|node|nodejs|deno|bun|bash|sh|zsh|fish|ruby|perl|php|lua|Rscript|pwsh|tclsh(?:\d+(?:\.\d+)*)?|wish)\Z')
DECLARATIONS = re.compile(r'(?m)(?:\b(?:def|class|function|fn|func)\s+([A-Za-z_]\w*)|^\s*(?:export\s+)?(?:const\s+|let\s+|var\s+)?([A-Za-z_]\w*)\s*(?:=|:))')


def edited_forms(event, target):
    """Return code/data name forms for a recorded effect, or None."""
    path = target.removeprefix('file:')
    suffix = ntpath.splitext(path)[1].lstrip('.').lower()
    content = '\n'.join(value for _, value in leaves(event.get('tool_input', {})))
    payloads = [value for key, value in leaves(event.get('tool_input', {}))
                if key and key[-1] in ('content', 'new_string', 'old_string', 'new_source')]
    structured = False
    for value in payloads:
        try:
            structured |= isinstance(json.loads(value), (dict, list))
        except (ValueError, TypeError):
            pass
    shebang = bool(re.search(r'(?m)^#!\s*\S+', content))
    absolute = identity(target, event)[5:]
    executable = not suffix and os.path.isfile(absolute) and os.access(absolute, os.X_OK)
    record = (suffix in RECORD_SUFFIXES or not suffix and ntpath.basename(path) not in CONFIG_FILES and not executable) and event.get('tool_name') != 'NotebookEdit'
    data_form = (suffix in DATA_SUFFIXES or ntpath.basename(path) == '.env' or record) and event.get('tool_name') != 'NotebookEdit'
    data = data_form and not shebang
    if not (record or executable or suffix in CODE_SUFFIXES | DATA_SUFFIXES
            or ntpath.basename(path) in CONFIG_FILES
            or event.get('tool_name') == 'NotebookEdit'
            or re.search(r'(?m)^#!\s*\S+', content)
            or suffix not in ('md', 'rst', 'adoc') and (DECLARATIONS.search(content) or structured)):
        return None
    aliases = {s.text for s in names(content) if s.kind == 'identifier'}
    aliases.update(value for match in DECLARATIONS.finditer(content) for value in match.groups() if value)
    # JSON/YAML keys and dotted module names are also syntactic identifiers.
    aliases.update(re.findall(r'(?:^|[\n{,])\s*["\x27]([A-Za-z_]\w*)["\x27]\s*:', content))
    stem = ntpath.splitext(ntpath.basename(path))[0]
    if re.fullmatch(r'[A-Za-z_]\w*', stem):
        aliases.add(stem)
    relative = relative_path(absolute, event.get('cwd') or os.getcwd())
    module = ntpath.splitext(relative)[0].replace('/', '.') if relative is not None else ''
    if re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', module):
        aliases.add(module.removesuffix('.__init__'))
    return {'subject': identity(target, event), 'display': target, 'aliases': aliases,
            'data': data, 'data_form': data_form, 'record': record}


def full_read_subjects(pre, post):
    """Only completed full-file reads, never a search, slice or status receipt."""
    from .observed import failed
    response = post.get('tool_response')
    if failed(post) or response is None:
        return set()
    if isinstance(response, dict):
        if any(response.get(key) for key in ('backgroundTaskId', 'session_id', 'sessionId', 'running', 'truncated', 'is_truncated')):
            return set()
        if not any(isinstance(response.get(key), str) for key in ('content', 'stdout', 'output')):
            return set()
    elif not isinstance(response, str):
        return set()
    ti, tool = pre.get('tool_input', {}), pre.get('tool_name')
    targets = []
    if tool == 'Read' and not any(key in ti for key in ('offset', 'limit', 'start_line', 'end_line', 'pages')):
        if ti.get('file_path'):
            targets.append(ti['file_path'])
    elif tool == 'Bash':
        words = simple_argv(ti.get('command', ''))
        if words and program_name(words[0]) == 'cat':
            args = words[1:]
            if args and args[0] == '--':
                args = args[1:]
            # One operand keeps returned bytes attributable to that same file.
            if len(args) == 1 and args[0] and args[0] != '-' and not args[0].startswith('-'):
                targets.extend(args)
    if tool == 'Bash':
        targets.extend(json_loaded_paths(ti.get('command', '')))
    for event in (pre, post):
        targets.extend(spec['subject'] for spec in event.get('makoto', {}).get('reads', [])
                       if spec.get('complete') is True and not spec.get('producer') and spec.get('role') != 'relay')
    return {identity(target, pre) for target in targets}


JSON_LOAD = re.compile(
    r"""json\.load\(\s*open\(\s*(['"])([^'"$*?`]+)\1\s*\)\s*\)"""
    r"""|json\.loads\(\s*open\(\s*(['"])([^'"$*?`]+)\3\s*\)\.read\(\s*\)\s*\)""")


def json_loaded_paths(command):
    """Files a successful `python -c` parsed whole with json.load on a literal path.

    json.load either consumes the entire file or raises, so a call that exits
    zero read the file in full. Statements joined by `;` hide an earlier
    failure behind a later exit status, so only a lone call or an `&&` chain
    counts.
    """
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=';&|()<>\n')
        lex.whitespace_split = True
        words = list(lex)
    except ValueError:
        return []
    statements, current = [], []
    for word in words:
        if word == '&&':
            statements.append(current)
            current = []
        elif word and all(c in ';&|()<>\n' for c in word):
            return []
        else:
            current.append(word)
    statements.append(current)
    paths = []
    for argv in statements:
        if len(argv) == 3 and re.fullmatch(r'python3?(?:\.\d+)?', program_name(argv[0])) and argv[1] == '-c':
            for match in JSON_LOAD.finditer(argv[2]):
                paths.append(match.group(2) or match.group(4))
    return paths


def names_change(event, change):
    """Every ship after code edits counts; writers require a literal name.

    A final answers for what its own agent wrote: a subagent's Stop is not held
    for a sibling worker's file. Commit and push still ship every agent's edits.
    """
    if event.get('tool_name') == 'Bash' and git_action(event):
        return True
    if event['hook_event_name'] in FINAL:
        return change.get('agent') == event.get('agent_id')
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
    if any(contains(text, value, 'path') for value in path_spellings(absolute, event.get('cwd') or os.getcwd())):
        return True
    # Keys and stems of a data file are its schema. A writer producing another
    # data file with the same keys is authoring a sibling, not naming this one.
    writer = ti.get('file_path') or ti.get('notebook_path') or ''
    if change.get('data_form') and ntpath.splitext(writer)[1].lstrip('.').lower() in CONFIG_SUFFIXES:
        return False
    return any(contains(text, alias, 'identifier') for alias in change['aliases'])


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
        redirects = []
        if not words:
            parsed = redirected_argv(ti.get('command', ''))
            if parsed:
                words = simple_argv(shlex.join(parsed[0]))
                redirects = parsed[1]
        # The launcher records the script payload after --. The normal parser
        # keeps interpreter check/eval flags and output requirements intact.
        launcher = words[1:] if words and program_name(words[0]) in ('sh', 'bash', 'zsh') else words
        if (len(launcher) >= 4 and program_name(launcher[0]) == 'codex-job.sh'
                and launcher[1] == 'start' and '--' in launcher[3:]):
            payload = launcher[launcher.index('--', 3) + 1:]
            if payload:
                nested = dict(pre, tool_input=dict(ti, command=shlex.join(payload)))
                targets.extend(s.removeprefix('file:') for s in execution_subjects(nested, changes, post))
        if words:
            program = program_name(words[0])
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
                    if program.startswith(('python', 'pypy')) and arg == '-c' and i + 1 < len(args):
                        # Only unconditional, top-level import syntax identifies
                        # modules run by an inline Python invocation.
                        try:
                            body = ast.parse(args[i + 1]).body
                        except SyntaxError:
                            body = []
                        modules = []
                        for statement in body:
                            if isinstance(statement, ast.Import):
                                modules.extend(alias.name for alias in statement.names)
                            elif isinstance(statement, ast.ImportFrom) and not statement.level and statement.module:
                                modules.append(statement.module)
                            else:
                                # Explicit whole-file config consumption, with
                                # no arbitrary call/conditional before the load.
                                expression = statement.value if isinstance(statement, ast.Expr) else None
                                if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name) and expression.func.id == 'print' and len(expression.args) == 1 and not expression.keywords:
                                    expression = expression.args[0]
                                if (isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute)
                                        and isinstance(expression.func.value, ast.Name)
                                        and expression.func.value.id in ('json', 'tomllib') and expression.func.attr == 'load'
                                        and len(expression.args) == 1 and not expression.keywords):
                                    opened = expression.args[0]
                                    if (isinstance(opened, ast.Call) and isinstance(opened.func, ast.Name)
                                            and opened.func.id == 'open' and not opened.keywords
                                            and 1 <= len(opened.args) <= 2 and isinstance(opened.args[0], ast.Constant)
                                            and isinstance(opened.args[0].value, str)
                                            and (len(opened.args) == 1 or isinstance(opened.args[1], ast.Constant)
                                                 and opened.args[1].value in ('r', 'rb'))):
                                        path = opened.args[0].value
                                        if path and changes.get(identity(path, pre), {}).get('data'):
                                            targets.append(path)
                                break  # Earlier arbitrary code may exit/raise.
                        for module in modules:
                            candidates = [identity(module.replace('.', '/') + ending, pre)
                                          for ending in ('.py', '/__init__.py')]
                            matches = [value for value in candidates if value in changes]
                            if len(matches) == 1:
                                targets.append(matches[0].removeprefix('file:'))
                        break
                    if program in ('node', 'nodejs') and arg in ('-e', '--eval') and i + 1 < len(args):
                        literal = r'(\x27[^\x27\\]*\x27|"[^"\\]*")'
                        vm = re.fullmatch(r'''\s*require\(['"](?:node:)?vm['"]\)\.runInNewContext\(\s*require\(['"](?:node:)?fs['"]\)\.readFileSync\(\s*'''
                                          + literal + r'''\s*,\s*['"]utf8['"]\s*\)\s*,\s*\{\s*console\s*\}\s*\)\s*;?\s*''', args[i + 1])
                        if vm:
                            targets.append(vm[1][1:-1])
                        break
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
            elif program in ('sqlite3', 'psql', 'mysql'):
                targets.extend(target for operator, target in redirects if operator == '<'
                               and not any(c in target for c in '$*?`'))
                if program == 'psql' and '-f' in words and words.index('-f') + 1 < len(words):
                    targets.append(words[words.index('-f') + 1])
            elif program in ('awk', 'gawk', 'mawk', 'nawk'):
                for i, word in enumerate(words[1:], 1):
                    if word in ('-f', '--file') and i + 1 < len(words):
                        targets.append(words[i + 1])
                    elif word.startswith('--file='):
                        targets.append(word.split('=', 1)[1])
                    elif word.startswith('-f') and len(word) > 2:
                        targets.append(word[2:])
            elif program == 'go' and len(words) > 2 and words[1] == 'run':
                targets.extend(w for w in words[2:] if w.endswith('.go') and not w.startswith('-'))
            elif program == 'jupyter' and len(words) > 2 and words[1] == 'nbconvert' and '--execute' in words[2:]:
                targets.extend(w for w in words[2:] if w.endswith('.ipynb') and not w.startswith('-'))
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
    return {identity(target, pre) for target in targets if target != ''}


def compiled_subjects(pre):
    """An explicit native compiler source -> -o product link, never a run."""
    words = simple_argv(pre.get('tool_input', {}).get('command', ''))
    if not words:
        return None
    program = program_name(words[0])
    if program not in ('cc', 'gcc', 'clang', 'c++', 'g++', 'clang++', 'rustc'):
        return None
    if any(w in ('-c', '-S', '-E', '-fsyntax-only', '--emit=metadata') for w in words):
        return None
    if '-o' not in words or words.index('-o') + 1 >= len(words):
        return None
    output = words[words.index('-o') + 1]
    sources = [w for w in words[1:] if w != output and not w.startswith('-')
               and ntpath.splitext(w)[1] in ('.c', '.cc', '.cpp', '.cxx', '.rs')]
    if not output or not sources:
        return None
    return identity(output, pre), {identity(source, pre) for source in sources}


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
