"""Conservative lexical command order; never evaluates shell text."""
import re
import shlex
from functools import lru_cache


@lru_cache(maxsize=512)
def redirected_argv(command):
    """Separate unquoted static redirects from a single command's argv."""
    parts = ordered_segments(command)
    if parts is None or len(parts) != 1:
        return None
    try:
        lex = shlex.shlex(parts[0][0], posix=False, punctuation_chars='<>')
        lex.whitespace_split = True
        raw = list(lex)
        if not any(word in ('<', '>', '>>', '>|', '<<', '<<-') for word in raw):
            # Decode adjacent shell quote fragments together. Preserve native
            # Windows path operands that the host recorded without quoting.
            native = parts[0][0]
            for word in raw:
                if re.match(r'^(?:[A-Za-z]:\\|\\\\)[^\s]+$', word):
                    native = native.replace(word, shlex.quote(word))
            return tuple(shlex.split(native)), ()
        words, redirects = [], []
        i = 0
        while i < len(raw):
            word = raw[i]
            if word in ('<', '>', '>>', '>|', '<<', '<<-'):
                if i + 1 >= len(raw):
                    return None
                target = shlex.split(raw[i + 1])[0]
                if words and words[-1].isdigit():
                    words.pop()  # descriptor prefix, e.g. 2>errors.txt
                redirects.append((word, target))
                i += 2
                continue
            # Native recorded Windows operands retain their path separators.
            decoded = [word] if re.match(r'^(?:[A-Za-z]:\\|\\\\)[^\s]+$', word) else shlex.split(word)
            if len(decoded) != 1:
                return None
            words.append(decoded[0])
            i += 1
        return tuple(words), tuple(redirects)
    except (ValueError, IndexError):
        return None


@lru_cache(maxsize=512)
def ordered_segments(command):
    """Return (command, preceding separator) pairs, or None for opaque syntax.

    Quotes, escapes, comments and nested substitutions protect separators.
    Heredoc bodies are consumed as data, not commands. Shell compound control
    flow, subshells and background jobs deliberately retain the legacy adapter.
    """
    parts, current, docs = [], [], []
    link, quote, stack = None, None, []
    i = 0

    def flush(separator):
        nonlocal current, link
        text = ''.join(current).strip()
        if text:
            parts.append((text, link))
        current, link = [], separator

    while i < len(command):
        c = command[i]
        if c == '\\' and quote != "'":
            if i + 1 == len(command):
                return None
            current.append(command[i:i + 2] if command[i + 1] != '\n' else '')
            i += 2
            continue
        if quote:
            current.append(c)
            if c == quote:
                quote = None
            elif c == '$' and quote == '"' and command[i:i + 2] == '$(':
                # Substitution quotes are independent of the enclosing quote.
                stack.append((')', quote))
                quote = None
                current.append('(')
                i += 1
            i += 1
            continue
        if c in "'\"`":
            quote = c
            current.append(c)
        elif command[i:i + 2] in ('$(', '${'):
            stack.append((')' if command[i + 1] == '(' else '}', None))
            current.append(command[i:i + 2])
            i += 1
        elif stack:
            current.append(c)
            if c == '(' and stack[-1][0] == ')':
                stack.append((')', None))
            elif c == stack[-1][0]:
                _, quote = stack.pop()
        elif c == '#' and (not current or current[-1][-1:].isspace()):
            end = command.find('\n', i)
            i = len(command) if end < 0 else end
            continue
        elif command[i:i + 2] == '<<':
            match = re.match(r'<<(-?)\s*(\x27[^\x27\n]+\x27|"[^"\n]+"|[\w.-]+)', command[i:])
            if not match:
                return None
            docs.append((shlex.split(match[2])[0], bool(match[1])))
            current.append(match[0])
            i += len(match[0]) - 1
        elif c in '(){}' or c == '&' and command[i:i + 2] != '&&':
            # & in a redirect is not a background operator.
            if c == '&' and current and current[-1].endswith(('>', '<')):
                current.append(c)
            else:
                return None
        elif c in ';|&\n':
            separator = c
            if command[i:i + 2] in ('&&', '||'):
                separator = command[i:i + 2]
                i += 1
            if command[i:i + 2] in (';;', '|&'):
                return None
            flush(separator)
            if c == '\n' and docs:
                i += 1
                for delimiter, tabs in docs:
                    while i < len(command):
                        end = command.find('\n', i)
                        end = len(command) if end < 0 else end
                        line = command[i:end]
                        i = end + (end < len(command))
                        if (line.lstrip('\t') if tabs else line) == delimiter:
                            break
                    else:
                        return None
                    if (line.lstrip('\t') if tabs else line) != delimiter:
                        return None
                docs = []
                continue
        else:
            current.append(c)
        i += 1
    if quote or stack or docs:
        return None
    flush(None)
    for text, _ in parts:
        try:
            first = shlex.split(text)[0]
        except (ValueError, IndexError):
            return None
        if first in ('if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'until', 'do', 'done', 'case', 'esac', 'function', 'select', '!', 'coproc'):
            return None
    return tuple(expand_assigned(parts))


ASSIGN = re.compile(r'(?:export\s+)?([A-Za-z_]\w*)=(\S*)')


def expand_assigned(parts):
    """Expand $NAME and ${NAME} from an earlier literal NAME=value segment of the same command."""
    env, out = {}, []
    for text, link in parts:
        words = text.split("'")
        text = "'".join(w if i % 2 else re.sub(r'\$(?:\{(\w+)\}|([A-Za-z_]\w*))',
                        lambda m: env.get(m[1] or m[2], m[0]), w) for i, w in enumerate(words))
        out.append((text, link))
        match = ASSIGN.fullmatch(text.strip())
        if match:
            try:
                value = shlex.split(match[2])
            except ValueError:
                value = []
            if len(value) == 1 and re.fullmatch(r'[\w./:@%+,=-]+', value[0]):
                env[match[1]] = value[0]
    return out


def selected_segments(command, post):
    """Resolve literal short circuits; uncertain branch selection stays opaque."""
    parts = ordered_segments(command)
    if parts is None:
        return None
    response = post.get('tool_response')
    success = post.get('hook_event_name') != 'PostToolUseFailure' and not (
        isinstance(response, dict) and (response.get('is_error') or response.get('isError')
        or next((response[k] for k in ('exitCode', 'exit_code', 'exit') if k in response), 0)))
    selected, status = [], None
    for text, link in parts:
        if link == '&&' and status is False or link == '||' and status is True:
            continue
        if link == '||' and status is None or link == '&&' and status is None and not success:
            return None
        selected.append(text)
        words = shlex.split(text)
        status = True if words == ['true'] or words == [':'] else False if words == ['false'] else None
    return selected
