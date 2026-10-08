"""Recorded file paths are portable identities, independent of the hook host."""
import ntpath
import posixpath
import re


def flavour(*paths):
    return ntpath if any(ntpath.splitdrive(path)[0] for path in paths) else posixpath


def normalized_path(path, cwd):
    """Bind relative paths and retain drives/UNC roots, using '/' in keys."""
    path, cwd = path.replace('\\', '/'), cwd.replace('\\', '/')
    paths = flavour(path, cwd)
    return paths.normpath(paths.join(cwd, path)).replace('\\', '/')


def relative_path(path, cwd):
    """A different drive/share has no relative spelling; never call relpath."""
    path, cwd = path.replace('\\', '/'), cwd.replace('\\', '/')
    paths = flavour(path, cwd)
    if paths is ntpath and ntpath.splitdrive(path)[0].lower() != ntpath.splitdrive(cwd)[0].lower():
        return None
    return paths.relpath(path, cwd).replace('\\', '/')


def path_spellings(path, cwd):
    """Equivalent separator spellings for output paths and change references."""
    spellings = {path}
    relative = relative_path(path, cwd)
    if relative is not None:
        spellings.update((relative, './' + relative))
    return spellings | {value.replace('/', '\\') for value in spellings}


def program_name(path):
    """Bash may invoke a Windows executable with either separator."""
    name = ntpath.basename(path)
    return name[:-4] if name.lower().endswith('.exe') else name


def subject_path(path):
    """Reject syntax tokens and unresolved shell names before path identity."""
    token = ntpath.basename(path.removeprefix('file:'))
    return bool(token and any(c.isalnum() for c in token)
                and not re.fullmatch(r'\d+:', token)
                and not re.search(r'\$(?:[A-Za-z_]\w*|\{[^}]+\})', path))
