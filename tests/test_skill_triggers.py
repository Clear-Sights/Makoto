"""Replay public typed moments through the shipped hook commands."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugin'
FIXTURES = ROOT / 'tests/fixtures/skill_triggers'
MOMENTS = json.loads((FIXTURES / 'moments.json').read_text())
MAPS = json.loads((PLUGIN / 'skill_triggers/hooks/trigger-map.json').read_text())['maps']


@pytest.fixture
def runtime(tmp_path):
    home = tmp_path / 'home'
    for mapping in MAPS:
        skill = mapping['skill']
        target = home / '.claude/skills/synced/current' / skill / 'SKILL.md'
        target.parent.mkdir(parents=True)
        shutil.copyfile(FIXTURES / skill / 'SKILL.md', target)
    env = {**os.environ, 'HOME': str(home), 'CLAUDE_PLUGIN_ROOT': str(PLUGIN)}
    env.pop('CLAUDE_PLUGIN_DATA', None)
    return home, env


def run(env, kind, event):
    hooks = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks']
    commands = [h['command'] for group in hooks[kind] for h in group['hooks']
                if '/skill_triggers/' in h['command']]
    assert len(commands) == 1
    result = subprocess.run(commands[0], shell=True, env=env, input=json.dumps(event),
                            text=True, capture_output=True, timeout=10)
    assert result.returncode == 0
    assert result.stderr == ''
    if not result.stdout:
        return None
    output = json.loads(result.stdout)
    assert set(output) == {'hookSpecificOutput'}
    output = output['hookSpecificOutput']
    assert set(output) == {'hookEventName', 'additionalContext'}
    assert output['hookEventName'] == kind
    return output['additionalContext']


@pytest.mark.parametrize('moment', MOMENTS)
def test_moment(runtime, moment):
    home, env = runtime
    event = {**moment['event'], 'session_id': 'fixture'}
    context = run(env, 'PreToolUse', event)
    if moment['owner'] == 'none':
        assert context is None
        return
    assert context.startswith('Skill source: ' + moment['owner'] + '=installed:')
    assert str(home) in context.splitlines()[0]
    assert sorted(re.findall(r'<!-- rule_id: ([A-Z]+\d+) -->', context)) == moment['rules']
    assert run(env, 'PreToolUse', event) is None


def test_session_start(runtime):
    _, env = runtime
    context = run(env, 'SessionStart', {})
    residents = [rid for m in MAPS for rid in m['resident_rules']]
    assert [line.split(':', 1)[0] for line in context.splitlines()[1:]] == residents
    assert len(context.splitlines()) == 1 + len(residents)


@pytest.mark.parametrize('plant', ['broken-map', 'crash', 'missing-script'])
def test_failure_plants(runtime, tmp_path, plant):
    _, env = runtime
    copy = tmp_path / 'plugin'
    shutil.copytree(PLUGIN / 'skill_triggers', copy / 'skill_triggers')
    env['CLAUDE_PLUGIN_ROOT'] = str(copy)
    hooks = copy / 'skill_triggers/hooks'
    if plant == 'broken-map':
        (hooks / 'trigger-map.json').write_text('{bad map')
    elif plant == 'crash':
        target = hooks / 'trigger.py'
        target.write_text(target.read_text().replace('    root = Path(',
                          "    raise RuntimeError('plant')\n    root = Path(", 1))
    else:
        (hooks / 'trigger.py').unlink()
    for kind in ('SessionStart', 'PreToolUse'):
        assert run(env, kind, {'session_id': 'fixture', 'situation_classes': ['handoff']}) is None


def test_missing_skill_and_precedence(runtime):
    home, env = runtime
    synced = home / '.claude/skills/synced/current'
    shutil.rmtree(synced / 'adversarial-review')
    assert run(env, 'PreToolUse', {'session_id': 'fixture',
               'situation_classes': ['claim_replay', 'handoff']}) is None
    assert 'cheap-execution=' in run(env, 'SessionStart', {})
    assert run(env, 'PreToolUse', {'session_id': 'fixture',
               'situation_classes': ['handoff']})
    shutil.rmtree(synced)
    for kind in ('SessionStart', 'PreToolUse'):
        assert run(env, kind, {'session_id': 'empty', 'situation_classes': ['handoff']}) is None


def test_sources_edits_and_state(runtime, tmp_path):
    home, env = runtime
    synced = home / '.claude/skills/synced/current/cheap-execution/SKILL.md'
    direct = home / '.claude/skills/cheap-execution/SKILL.md'
    direct.parent.mkdir(parents=True)
    shutil.copyfile(synced, direct)
    event = {'session_id': 'fixture', 'situation_classes': ['handoff']}
    assert str(synced) in run(env, 'PreToolUse', event)
    state = home / '.cache/makoto/skill-triggers/fixture/rules.json'
    assert state.is_file()
    context = run(env, 'PreToolUse', {**event, 'situation_classes': ['bill', 'handoff']})
    assert 'rule_id: C9' in context and 'rule_id: C1' not in context
    synced.unlink()
    direct.write_text(direct.read_text().replace('rule_id: C1 -->\nDo: ', 'rule_id: C1 -->\nDo: Fixture edit ', 1))
    env['CLAUDE_PLUGIN_DATA'] = str(tmp_path / 'data')
    context = run(env, 'PreToolUse', event)
    assert str(direct) in context and 'Fixture edit' in context
    assert (tmp_path / 'data/skill-triggers/fixture/rules.json').is_file()


@pytest.mark.parametrize('event', [None, [], {'situation_classes': 3},
    {'session_id': '../escape', 'situation_classes': ['handoff']}])
def test_invalid_payload(runtime, event):
    _, env = runtime
    assert run(env, 'PreToolUse', event) is None


def test_public_privacy():
    paths = [p for base in (PLUGIN / 'skill_triggers', FIXTURES)
             for p in base.rglob('*') if p.is_file()]
    paths.extend([Path(__file__), PLUGIN / 'hooks/hooks.json',
                  PLUGIN / '.claude-plugin/plugin.json',
                  ROOT / '.claude-plugin/marketplace.json'])
    patterns = [r'/mnt/' + r'project-files', r'/home/user/' + r'ssm',
                r'cmsg' + r'_|cse' + r'_',
                r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}',
                r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',
                r'(?:sess_|session[-_:])[A-Za-z0-9]{8,}', r'\bL[0-9]{2,}\b',
                r'(?m)^<!-- contract: \{', r'(?m)^Evidence:|^Default:|^Needs:',
                r'(?im)^(?:memory text|BEGIN PRIVATE|private excerpt|# Memory|<memory)']
    section = (ROOT / 'README.md').read_text().split('## Skill triggers\n', 1)[1].split('\n## ', 1)[0]
    for pattern in patterns:
        assert not re.search(pattern, section)
    for path in paths:
        assert not path.is_symlink()
        text = path.read_text()
        for pattern in patterns:
            assert not re.search(pattern, text), (path, pattern)
        if path.name == 'SKILL.md':
            lines = text.splitlines()
            assert len(lines) <= 22
            assert all(re.fullmatch(r'<!-- rule_id: [A-Z]+\d+ -->|Do: .+', line)
                       for line in lines)
    assert not list((PLUGIN / 'skill_triggers').rglob('SKILL.md'))
