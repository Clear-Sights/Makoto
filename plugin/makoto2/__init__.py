"""Build a portable Makoto package from the current source tree."""

import hashlib
import json
from pathlib import Path
import shutil


PLUGIN_METADATA = {
    'name': 'makoto',
    'version': '5.0.0-dev',
    'description': 'Executable lifecycle and hook decisions over current observations.',
}


def build_package(root, destination):
    """Copy shipped runtime assets into a new, independently removable directory.

    Evidence and local state are never package inputs. Existing destinations
    are refused so packaging cannot replace an installed package or user files.
    """
    root = Path(root).resolve()
    destination = Path(destination).resolve()
    source = root / 'plugin'
    version = PLUGIN_METADATA['version']
    if not (source / 'makoto2' / '__main__.py').is_file():
        raise FileNotFoundError(source / 'makoto2' / '__main__.py')
    if destination == root or root in destination.parents:
        raise ValueError('Package destination must be outside the source tree')
    if destination.exists():
        raise FileExistsError(destination)

    destination.mkdir(parents=True)
    try:
        ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo')
        shutil.copytree(source, destination, dirs_exist_ok=True, ignore=ignore)
        metadata_dir = destination / '.claude-plugin'
        metadata_dir.mkdir(exist_ok=True)
        (metadata_dir / 'plugin.json').write_text(
            json.dumps(PLUGIN_METADATA, indent=2) + '\n', encoding='utf-8')
        (destination / 'UNINSTALL.md').write_text(
            'To uninstall, remove this package directory and any hook entries '
            'you configured to invoke it. Session state is separate; remove '
            'your configured state directory only if you also want to erase '
            'the retained session history.\n', encoding='utf-8')
        contents = {str(path.relative_to(destination)): path.read_bytes()
                    for path in sorted(destination.rglob('*')) if path.is_file()}
        pins = {name: hashlib.sha256(data).hexdigest()
                for name, data in contents.items()}
        digest = hashlib.sha256(json.dumps(
            pins, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {'path': str(destination), 'version': version,
            'contents': contents, 'input_digest': digest}
