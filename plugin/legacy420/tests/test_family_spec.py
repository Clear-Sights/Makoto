"""Literal boundaries for SPEC, independent of any owner vocabulary."""
from makoto2 import family_spec as s, observed


def rec(*events):return observed.record(events)
def pre(tool='Write',**ti):return dict(hook_event_name='PreToolUse',tool_name=tool,tool_input=ti)
def post(command,exit):return dict(hook_event_name='PostToolUse',tool_name='Bash',tool_input={'command':command},tool_response={'exitCode':exit})

def test_zip_requires_literal_true_and_dict_uses_python_equality():
    for text,entries in [('zip(a,b,strict=1)',{'A3'}),('zip(a,b,strict=True)',set()),("d={True:1,1:2}",{'A4'}),("d={1:1,2:2}",set())]:
        assert {e for f in s.spec_tree(rec(),pre(content=text),{}) for e in f['entries']}==entries


def test_loop_else_is_the_register_exclusion():
    assert s.spec_tree(rec(),pre(content='for x in rows:\n re.match(pattern,x)'),{})
    assert not s.spec_tree(rec(),pre(content='for x in rows:\n re.match(pattern,x)\nelse:\n report()'),{})


def test_named_sets_are_never_guessed():
    ev=pre(file_path='test_sample.py',content='pass')
    assert not s.spec_write(rec(),ev,{})
    cfg={'named_sets':{'TEST_PATH':[r'test_.*\.py$']}}
    assert s.spec_write(rec(),ev,cfg)[0]['entries']==['B2','B5','B20']


def test_repeat_uses_any_prior_qualifying_exit_and_last_command_boundary():
    ev=pre('Bash',command='verify')
    # A subsequent green run does not erase seen(exit!=0).
    assert s.spec_repeat(rec(post('verify',1),post('verify',0)),ev,{})
    edit=pre('Edit',file_path='source',new_string='fix')
    assert not s.spec_repeat(rec(post('verify',1),edit),ev,{})
    assert s.spec_repeat(rec(post('verify',1),edit,post('verify',0)),ev,{})


def test_agent_boundary_and_verifier_are_separate_history_variables():
    a=pre('Agent',prompt='first');b=pre('Agent',prompt='second')
    assert s.spec_history(rec(a,post('verify',1),b),a,{})
    assert not s.spec_history(rec(a,b,post('verify',1)),a,{})


def test_pre_events_never_become_settled_observations():
    event=pre('Agent',prompt='first');r=rec(event)
    event['tool_input']['prompt']='changed'
    assert r.events[0]['tool_input']['prompt']=='first'
    assert not r.obs


def test_i1_tests_label_presence_not_filled_cells_and_only_agent():
    cfg={'settings':{'makoto':{'dispatch':True}}};brief='READ:\nWRITE:\nACCEPTANCE:'
    assert not s.spec_claim(rec(),pre('Agent',prompt=brief),cfg)
    assert s.spec_claim(rec(),pre('Agent',prompt='READ:'),cfg)
    assert not s.spec_claim(rec(),pre('Task',prompt='READ:'),cfg)


def test_budget_reads_elapsed_and_preserves_equality():
    assert s.spec_budget(rec(),dict(run='suite',elapsed=0,budget=0),{})
    assert not s.spec_budget(rec(),dict(run='suite',elapsed=1,budget=2,timeout=100),{})


def test_authorship_membership_is_exact_while_messages_match():
    cfg={'named_sets':{'MODEL':['model-author']}}
    assert not s.spec_authorship(rec(),dict(run='git log base..HEAD',commits=[{'author':'model-author-assistant'}]),cfg)
    assert s.spec_authorship(rec(),dict(run='git log base..HEAD',commits=[{'message':'by model-author'}]),cfg)
