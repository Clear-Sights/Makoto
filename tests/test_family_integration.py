"""Shared hook boundaries: declared tables, known anchors, and native SWITCH calls."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'plugin'))
from makoto2 import observed,evaluate,hook


def candidate():
    plugin=Path(__file__).resolve().parents[1]/'plugin/makoto2'
    cfg=evaluate.load_cfg(str(plugin/'config.json'))
    return cfg,evaluate.load_rows(str(plugin/'rows.tsv'),cfg)


def test_user_anchor_is_required_for_post_user_baseline():
    cfg,rows=candidate()
    event={'hook_event_name':'PreToolUse','tool_name':'Agent','tool_input':{'prompt':'Inspect'}}
    assert evaluate.evaluate(rows,observed.record([]),event) is None
    finding=evaluate.evaluate(rows,observed.record([{'hook_event_name':'UserPromptSubmit','prompt':'Inspect'}]),event)
    assert finding and 'B11' in finding['message']


def test_switch_ast_is_routed_from_native_write():
    cfg,rows=candidate()
    event={'hook_event_name':'PreToolUse','tool_name':'Write','tool_input':{'file_path':'source.py','content':'match value:\n case 1: print(value)'}}
    finding=evaluate.evaluate(rows,observed.record([]),event)
    assert finding and finding['row']=='SWITCH.fallthrough'


def test_workspace_supplies_named_sets_without_a_default_vocabulary(tmp_path):
    (tmp_path/'makoto.toml').write_text('dispatch = false\n[named_sets]\nTEST_PATH = ["^checks/"]\n')
    cfg,rows=candidate();cfg['state_dir']=str(tmp_path/'state')
    event={'hook_event_name':'PreToolUse','session_id':'tables','cwd':str(tmp_path),'tool_name':'Write','tool_input':{'file_path':'checks/example','content':'print(1)'}}
    decision=hook.main(json.dumps(event),cfg,rows,observed.record,evaluate.evaluate)
    assert decision['hookSpecificOutput']['permissionDecision']=='deny'
    assert 'B2/B5/B20' in decision['hookSpecificOutput']['permissionDecisionReason']
