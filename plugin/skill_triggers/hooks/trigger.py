#!/usr/bin/env python3
"""Advisory only. Any failure produces no output and never blocks a tool."""
import json, os, sys, shlex, re
try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None
from pathlib import Path

def classify(event):
 explicit=event.get('situation_classes')
 if explicit is not None:
  if not isinstance(explicit,list) or any(not isinstance(c,str) for c in explicit):raise ValueError('invalid situation classes')
  return set(explicit)
 tool=event.get('tool_name',''); inp=event.get('tool_input') or {}
 classes=set()
 if tool=='Agent':return {'harness_launch','budget'}
 if tool in ('spawn_agent','collaboration.spawn_agent'):return {'launch'}
 if tool in ('Write','Edit','write_file'):
  p=Path(inp.get('file_path',inp.get('path','')))
  if 'PLANS' in p.parts or p.name.lower() in ('plan.md','handoff.md'):classes.add('handoff')
  return classes
 if tool not in ('Bash','exec_command','functions.exec_command'):return classes
 command=inp.get('command',inp.get('cmd',''))
 if not isinstance(command,str):return classes
 # shlex isolates executable positions, so echoed names do not become invocations.
 lex=shlex.shlex(command,posix=True,punctuation_chars=';&|()');lex.whitespace_split=True;lex.commenters='#'
 tokens=list(lex); segments=[];current=[]
 for t in tokens:
  if t in (';','&&','||','&','|','(',')'):
   if current:segments.append(current);current=[]
  else:current.append(t)
 if current:segments.append(current)
 for seg in segments:
  while seg and (seg[0] in ('nohup','env','command','exec') or re.match(r'^[A-Za-z_][A-Za-z0-9_]*=',seg[0])):seg=seg[1:]
  if not seg:continue
  exe=Path(seg[0]).name;args=seg[1:]
  if exe in ('echo','printf','cat','head','tail','rg','grep','less','sed'):continue
  if exe=='codex' and args and args[0] in ('exec','e'):classes.update(('harness_launch','budget'))
  if exe=='claude' and '-p' in args:classes.update(('harness_launch','budget'))
  if exe=='git' and args and args[0] in ('merge','commit','push'):classes.add('claim_replay')
  scripts=[]
  if exe in ('sh','bash','python','python3'):
   if '-c' in args:continue
   scripts=[Path(x).name for x in args if not x.startswith('-')][:1]
  else:scripts=[exe]
  for script in scripts:
   stem=Path(script).stem
   if stem in ('gate','check','plants','test','check_suite','audit'):classes.add('claim_replay')
   if stem in ('check','plants'):classes.add('check_validity')
   if stem in ('run','run_suite') and ('--real' in command or stem=='run_suite'):classes.add('suite_timing')
   if stem=='codex-wait':classes.add('harness_chain')
   if stem=='dispatch':classes.update(('harness_launch','budget'))
   if stem=='bill':classes.add('bill')
   if stem=='construction':pass
   if stem=='share':classes.add('budget')
   if stem=='readout':classes.add('claim_replay')
 return classes


def skill_source(root, skill):
    home = Path(os.environ.get('HOME') or Path.home())
    synced = sorted((home/'.claude/skills/synced').glob('*/'+skill+'/SKILL.md'))
    candidates = synced + [home/'.claude/skills'/skill/'SKILL.md']
    for path in candidates:
        if path.is_file():
            return path, 'installed'
    return None, None

def cards(text):
    parts = re.split(r'<!-- rule_id: ([A-Z]+\d+) -->', text)
    return {parts[i]: '<!-- rule_id: '+parts[i]+' -->'+parts[i+1] for i in range(1,len(parts),2)}

def main():
    root = Path(os.environ['CLAUDE_PLUGIN_ROOT'])/'skill_triggers'
    kind = sys.argv[1]
    event = json.load(sys.stdin)
    config = json.loads((root/'hooks/trigger-map.json').read_text())
    maps = config['maps']
    if len(maps)!=3 or set(m['skill'] for m in maps)!=set(config['precedence']):
        raise ValueError('invalid maps')
    loaded = {}
    for mapping in maps:
        path, label = skill_source(root, mapping['skill'])
        if path is None:
            continue
        parsed = cards(path.read_text())
        if not set(mapping['rule_ids']) <= parsed.keys():
            raise ValueError('missing mapped rule')
        if set(mapping['classes']) != set(mapping['class_rule_ids']):
            raise ValueError('incomplete map')
        loaded[mapping['skill']] = (path,label,parsed)
    if kind == 'SessionStart':
        sources = []; lines = []
        for mapping in maps:
            if mapping['skill'] not in loaded:
                continue
            path,label,parsed = loaded[mapping['skill']]
            sources.append(mapping['skill']+'='+label+':'+str(path))
            for rid in mapping['resident_rules']:
                # A resident hint is one current Do line, not a full rule card.
                action = next(line[4:] for line in parsed[rid].splitlines() if line.startswith('Do: '))
                lines.append(rid+': '+action)
        if not lines:
            return
        context = 'Skill sources: '+'; '.join(sources)+'\n'+'\n'.join(lines)
        print(json.dumps({'hookSpecificOutput':{'hookEventName':kind,'additionalContext':context}}))
        return
    if kind != 'PreToolUse':
        raise ValueError('unknown event')
    classes = classify(event)
    mapping = next((m for skill in config['precedence'] for m in maps if m['skill']==skill and classes & set(m['classes'])),None)
    if mapping is None or mapping['skill'] not in loaded:
        return
    ids = set().union(*(set(mapping['class_rule_ids'][c]) for c in classes & set(mapping['classes'])))
    path,label,parsed = loaded[mapping['skill']]
    session = event['session_id']
    if not isinstance(session,str) or not session or session in ('.','..') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.' for c in session):
        raise ValueError('invalid session id')
    base = Path(os.environ.get('CLAUDE_PLUGIN_DATA') or str(Path(os.environ.get('HOME') or Path.home())/'.cache/makoto'))/'skill-triggers'
    state = base/session
    state.mkdir(parents=True,exist_ok=True)
    # Serialize the read/update so parallel tools cannot inject the same card twice.
    with (state/'lock').open('a') as lock:
        if fcntl:
            fcntl.flock(lock,fcntl.LOCK_EX)
        elif msvcrt:
            lock.seek(0)
            msvcrt.locking(lock.fileno(),msvcrt.LK_LOCK,1)
        record = state/'rules.json'
        seen = set(json.loads(record.read_text())) if record.exists() else set()
        fresh = [rid for rid in parsed if rid in ids and mapping['skill']+':'+rid not in seen]
        if not fresh:
            return
        context = 'Skill source: '+mapping['skill']+'='+label+':'+str(path)+'\n'+''.join(parsed[rid] for rid in fresh)
        output = json.dumps({'hookSpecificOutput':{'hookEventName':kind,'additionalContext':context}})
        seen.update(mapping['skill']+':'+rid for rid in fresh)
        temporary = state/'rules.tmp'
        temporary.write_text(json.dumps(sorted(seen)))
        temporary.replace(record)
        print(output)

if __name__ == '__main__':
    try:
        main()
    except BaseException:
        pass
