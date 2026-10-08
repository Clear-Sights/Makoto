"""Missing additional history preserves the public journal's evidence and holds."""
import json
from pathlib import Path

import pytest

from test_shapes import Session, event, pair, output
from makoto2 import hook
from run_pairs import held


def test_missing_transcript_retains_original_reading(tmp_path):
    s = Session(tmp_path)
    s.feed(pair(text='original_91'))
    candidate = dict(output('original_91'), transcript_path=str(tmp_path / 'missing.jsonl'))
    assert not held(s.send(candidate))
    assert s.rules() == set()
    assert len(s.journal()) == 3


def test_missing_transcript_retains_own_output_and_unread_file_holds(tmp_path):
    rows = pair('Write', {'file_path': 'owned.txt', 'content': 'own_value'}, 'written')
    rows += pair(ti={'file_path': 'owned.txt'}, text='own_value', tid='own')
    transcript = tmp_path / 'history.jsonl'
    transcript.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    s = Session(tmp_path)
    assert held(s.send(dict(output('owned.txt own_value'), transcript_path=str(transcript))))
    transcript.unlink()
    assert held(s.send(dict(output('owned.txt own_value'), transcript_path=str(transcript))))
    assert 'a' in s.rules()


@pytest.mark.parametrize('boundary', ['Stop', 'Write'])
def test_missing_transcript_cannot_recover_corrupt_journal(tmp_path, boundary):
    s = Session(tmp_path)
    s.feed(pair(text='original_91'))
    journal = hook.sigma_path(s.config['state_dir'], 'plant')
    journal.write_text(journal.read_text().replace('original_91', 'invented_91'))
    candidate = dict(output('original_91', boundary), stop_hook_active=False,
                     transcript_path=str(tmp_path / 'missing.jsonl'))
    response = s.send(candidate)
    assert held(response)
    assert 'corrupted journal chain' in str(response)


@pytest.mark.parametrize('fault', ['invalid', 'wrong-session', 'unreadable'])
def test_existing_bad_transcript_still_fails_closed(tmp_path, monkeypatch, fault):
    transcript = tmp_path / 'transcript.jsonl'
    transcript.write_text('not json\n' if fault == 'invalid' else
                          json.dumps(dict(event('UserPromptSubmit', prompt='go'), session_id='other')) + '\n')
    if fault == 'unreadable':
        original = Path.open
        def open_path(path, *args, **kwargs):
            if path == transcript:
                raise PermissionError('unreadable transcript')
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'open', open_path)
    s = Session(tmp_path)
    response = s.send(dict(output('Done'), stop_hook_active=False, transcript_path=str(transcript)))
    assert held(response)
    assert 'transport/contract failure' in str(response)
