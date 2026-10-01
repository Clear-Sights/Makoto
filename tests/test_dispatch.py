"""Workspace dispatch contracts extend existing rows without promoting Pre to Obs."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugin'))
from makoto2 import evaluate, hook, observed

PLUGIN = Path(__file__).resolve().parents[1] / 'plugin/makoto2'
BRIEF = 'READ: src/a.py@123456abcdef\nWRITE: src/a.py\nACCEPTANCE: sh verify.sh'


def run_session(tmp_path, declaration, prompt=BRIEF, run=None, claim='Done.'):
    if declaration is not None:
        (tmp_path / 'makoto.toml').write_text(declaration, encoding='utf-8')
    cfg = evaluate.load_cfg(str(PLUGIN / 'config.json'))
    cfg['state_dir'] = str(tmp_path / 'state')
    rows = evaluate.load_rows(str(PLUGIN / 'rows.tsv'), cfg)
    def send(event):
        event.update(cwd=str(tmp_path),session_id='dispatch-test')
        return hook.main(json.dumps(event),cfg,rows,observed.record,evaluate.evaluate)
    # B11 requires a post-user baseline probe independently of dispatch opt-in.
    send(dict(hook_event_name='PostToolUse', tool_name='Read',
              tool_input={'file_path':'baseline'}, tool_response={'content':'baseline'}))
    # Dispatch contract cases isolate pin/acceptance predicates after source reads.
    for name in evaluate.family_lineage.references(prompt, str(tmp_path), observed):
        path = Path(name)
        if path.is_absolute() and path.is_relative_to(tmp_path):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('source', encoding='utf-8')
            send(dict(hook_event_name='PostToolUse', tool_name='Read',
                      tool_input={'file_path':str(path)}, tool_response={'content':'source'}))
    first = send(dict(hook_event_name='PreToolUse',tool_name='Agent',tool_input=dict(prompt=prompt)))
    if first:
        return first, cfg
    if run:
        send(dict(hook_event_name='PostToolUse',tool_name='Bash',tool_input=run[0],tool_response=run[1]))
    return send(dict(hook_event_name='Stop',last_assistant_message=claim)), cfg


@pytest.mark.parametrize('declaration',[None,'dispatch = false','dispatch = "true"','dispatch = [','[other]\ndispatch = true'])
def test_optout_has_no_dispatch_contract(tmp_path,declaration):
    result,cfg=run_session(tmp_path,declaration,prompt='Fix the parser.')
    assert result == {}
    events,_=hook.sigma_read(hook.sigma_path(cfg['state_dir'],'dispatch-test'))
    assert cfg['dispatch'] is False
    assert all(o.tool != 'Agent' for o in observed.record(events).obs)


@pytest.mark.parametrize('prompt,row',[
    ('READ: src/a.py@123456abcdef\nWRITE:\nACCEPTANCE: sh verify.sh',None),
    (BRIEF.replace('@123456abcdef',''),'R08'),
    (BRIEF.replace('src/a.py@123456abcdef','src/a.py@123456abcdef src/b.py'),None),
    (BRIEF.replace('src/a.py@123456abcdef','src/a.py\n# tag@123456abcdef'),'R08'),
])
def test_read_line_has_the_register_pin(tmp_path,prompt,row):
    result,_=run_session(tmp_path,'dispatch = true',prompt=prompt,run=({'command':'sh verify.sh'},{'exitCode':0}),claim='Not done; waiting.')
    assert (row in json.dumps(result)) if row else result == {}


@pytest.mark.parametrize('run,claim,blocked',[
    (None,'Done.',True),
    (({'command':'sh verify.sh'},{'exitCode':0}),'Done.',False),
    (({'command':'sh verify.sh'},{'exitCode':1}),'Done.',True),
    (({'command':'sh verify.sh','run_in_background':True},{'exitCode':0}),'Done.',True),
    (({'command':'sh verify.sh'},{'exitCode':0,'backgroundTaskId':'job'}),'Done.',True),
    (({'command':'echo sh verify.sh'},{'exitCode':0}),'Done.',True),
    (None,'Not done; waiting.',True),
])
def test_only_settled_exact_acceptance_pays(tmp_path,run,claim,blocked):
    result,cfg=run_session(tmp_path,'dispatch = true',run=run,claim=claim)
    assert bool(result) is blocked
    if blocked:
        assert 'R11' in json.dumps(result)
    events,_=hook.sigma_read(hook.sigma_path(cfg['state_dir'],'dispatch-test'))
    assert all(o.tool != 'Agent' for o in observed.record(events).obs)
