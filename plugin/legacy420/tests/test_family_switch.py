"""Attacks on SWITCH operand boundaries and actual invocation semantics."""
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'plugin'))
from makoto2 import family_switch as f


def test_gate_invokes_each_check_and_denies_crash():
    calls=[]
    def crash(subject):
        calls.append(subject)
        raise RuntimeError('gate failed')
    assert f.switch_exit([crash,lambda s:SimpleNamespace(returncode=0)],'selected') == [1,0]
    assert calls == ['selected']


def test_zero_really_probes_every_removal_and_unrelated_rows():
    calls=[]
    def read(units):
        calls.append(units)
        return {'a','b'} if 'a' in units else set()
    result=f.switch_zero(('a','b'),read,{'a':'a','b':'b'})
    assert calls == [('a','b'),('b',),('a',)]
    assert result['simpler'] and result['unrelated']
    assert result['unrelated_units'] == ['a']


def test_test_write_operand_exclusions():
    event={'event':'Pre','tool':'Write','path':'tests/test_x.py','content':'print(1)'}
    assert f.switch_write(event,r'^tests/')
    for field,value in [('event','Stop'),('tool','Bash'),('path','src/x.py'),('content','expectation = 1')]:
        assert not f.switch_write(dict(event,**{field:value}),r'^tests/')


def test_failed_verifier_pays_doc_but_not_pass_claim():
    event={'event':'Pre','tool':'Edit','path':'docs/result.md','claim':{'kind':'pass','subject':'pytest subject'}}
    assert not f.switch_doc(event,[{'verifier':True,'exit':1}],r'^docs/')
    assert f.switch_pass(dict(event,event='Stop'),[{'command':'pytest subject','exit':1}])
    assert not f.switch_pass(dict(event,event='Stop'),[{'command':'pytest subject','exit':0}])


def test_match_capture_and_guard_are_not_wildcard():
    for pattern in ['captured','_ if value']:
        assert ('fallthrough',1) in f.switch_tree('match value:\n case '+pattern+': raise ValueError()')
    assert not f.switch_tree('match value:\n case _: raise ValueError()')


def test_run_predicate_requires_its_run_context():
    assert not f.switch_run({'run':'other','checks':{'a':1},'replay_sequence':False,'verdict':'fail'})
    assert f.switch_run({'shipped':{'enabled':False},'tested':{'enabled':True}}) == ['settings']
