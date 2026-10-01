"""Register ledger attacks: names pay individually and own outputs are not sources."""
from makoto2.lineage import unpaid
from makoto2.observed import record
from makoto2 import observed


def read(path,content):
    return dict(hook_event_name='PostToolUse',tool_name='Read',tool_input={'file_path':str(path)},tool_response={'content':content})


def act(tmp_path,text):
    return dict(hook_event_name='PreToolUse',cwd=str(tmp_path),tool_name='Write',tool_input={'file_path':str(tmp_path/'answer.md'),'content':text})


def test_each_reference_requires_its_own_read(tmp_path):
    first=tmp_path/'first.tsv';second=tmp_path/'second.tsv'
    first.write_text('one');second.write_text('two')
    r=record([read(first,'one')])
    assert unpaid(r,act(tmp_path,'first.tsv second.tsv'),observed)==[('unread',str(second))]
    r=record([read(first,'one'),read(second,'two')])
    assert not unpaid(r,act(tmp_path,'first.tsv second.tsv'),observed)


def test_source_changes_at_use_and_reread(tmp_path):
    source=tmp_path/'original.tsv';source.write_text('before')
    history=[read(source,'before')];source.write_text('after')
    assert unpaid(record(history),act(tmp_path,'original.tsv'),observed)==[('changed',str(source))]
    assert not unpaid(record(history+[read(source,'after')]),act(tmp_path,'original.tsv'),observed)


def test_reading_own_answer_does_not_create_a_source(tmp_path):
    source=tmp_path/'answer.tsv';source.write_text('own')
    write=dict(hook_event_name='PostToolUse',tool_name='Write',tool_input={'file_path':str(source),'content':'own'},tool_response={'type':'create'})
    assert unpaid(record([write,read(source,'own')]),act(tmp_path,'answer.tsv'),observed)==[('unread',str(source))]


def test_closing_reference_requires_read(tmp_path):
    source=tmp_path/'original.tsv';source.write_text('value')
    ev=dict(hook_event_name='Stop',cwd=str(tmp_path),last_assistant_message='original.tsv')
    assert unpaid(record([]),ev,observed)==[('unread',str(source))]
    assert not unpaid(record([read(source,'value')]),ev,observed)


def test_sentence_punctuation_is_not_part_of_the_source_name(tmp_path):
    source=tmp_path/'original.tsv';source.write_text('value')
    assert not unpaid(record([read(source,'value')]),act(tmp_path,'See original.tsv.'),observed)
