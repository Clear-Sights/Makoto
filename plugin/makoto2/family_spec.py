"""SPEC: one reading compared with the held REGISTER v9 definition.

Named sets come from cfg['named_sets']; no guessed vocabulary is installed.
Launch/run records are supplied by the gate that actually performs that run.
Each finding identifies all entries sharing the predicate, never one per copy.
"""
from __future__ import annotations
import ast
import os
import re
from pathlib import Path
from typing import NamedTuple


def finding(entries, subject, predicate, row='SPEC'):
    return dict(row=row, entries=list(entries), message="/".join(entries)+": "+predicate,
                objects=[str(subject)], predicate=predicate)


def args(event):
    value = event.get('tool_input')
    return value if isinstance(value, dict) else {}


def pre(event):
    return event.get('hook_event_name') == 'PreToolUse'


def stop(event):
    return event.get('hook_event_name') == 'Stop'


def content(event):
    ti = args(event)
    # Native Edit names are the adapter of register args.old/args.new.
    return str(ti.get('content', ti.get('new', ti.get('new_string', ''))))


def matches(cfg, name, value):
    """One owner-supplied table per named set; empty/unprovided means undefined."""
    return any(re.search(pattern, value) for pattern in cfg.get('named_sets', {}).get(name, ()))


def history(record):
    raw = getattr(record, 'events', None)
    if raw is not None:
        return raw
    return tuple(dict(hook_event_name='PostToolUseFailure' if o.failed else 'PostToolUse',
                      tool_name=o.tool, tool_input=o.input,
                      tool_response=dict(exitCode=o.exit, stdout=o.output)) for o in record.obs)


def exit_of(event):
    from makoto2 import observed
    response = event.get('tool_response')
    value = observed._exit_of(response, observed._flatten(response))
    failed = (event.get("hook_event_name") == "PostToolUseFailure" or
              isinstance(response, dict) and any(response.get(k) for k in ("is_error", "isError", "interrupted")))
    if failed:
        return value if value not in (None, 0) else 1
    return 0 if value is None and settled(event) and event.get("tool_name") == "Bash" else value


def settled(event):
    return event.get('hook_event_name') in ('PostToolUse', 'PostToolUseFailure')


def verifier_keys(record):
    return {str(args(e).get('command')) for e in history(record)
            if settled(e) and exit_of(e) not in (None, 0)}


def is_verifier(event, keys):
    return settled(event) and args(event).get('command') in keys


def spec_tree(record, event, cfg):
    if not (pre(event) and event.get('tool_name') in ('Write','Edit')):
        return []
    try:
        tree = ast.parse(content(event))
    except (SyntaxError, ValueError):
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'zip':
            strict = any(k.arg == 'strict' and isinstance(k.value, ast.Constant)
                         and k.value.value is True for k in node.keywords)
            if not strict:
                out.append(finding(('A3',), node.lineno, 'call=zip and not kw.strict=True'))
        if isinstance(node, ast.Dict):
            keys = []
            for key in node.keys:
                # Python key equality, including bool/int and numeric aliases.
                try:
                    value = ast.literal_eval(key)
                    hash(value)
                except (ValueError, TypeError, SyntaxError):
                    continue
                if value in keys:
                    out.append(finding(('A4',), node.lineno, 'keys.duplicated!={} and node=dict'))
                    break
                keys.append(value)
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)) and not node.orelse:
            body = ast.Module(body=node.body, type_ignores=[])
            # Residue handling belongs to the match's branch, not the loop's else.
            match_names = {target.id for assignment in ast.walk(body)
                           if isinstance(assignment, ast.Assign)
                           and isinstance(assignment.value, ast.Call)
                           and isinstance(assignment.value.func, ast.Attribute)
                           and isinstance(assignment.value.func.value, ast.Name)
                           and assignment.value.func.value.id == 're'
                           and assignment.value.func.attr in ('match', 'search')
                           for target in assignment.targets if isinstance(target, ast.Name)}
            has_residue = any(isinstance(n, ast.If) and n.orelse
                              and isinstance(n.test, ast.Name) and n.test.id in match_names
                              and any(isinstance(effect, (ast.Call, ast.Raise, ast.Return))
                                      and any(isinstance(value, ast.Name)
                                              and isinstance(value.ctx, ast.Load)
                                              and value.id in {target.id for target in ast.walk(getattr(node, 'target', ast.Constant(None)))
                                                               if isinstance(target, ast.Name)}
                                              for value in ast.walk(effect))
                                      for statement in n.orelse for effect in ast.walk(statement))
                              for n in ast.walk(body))
            if not has_residue and any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and isinstance(n.func.value, ast.Name) and n.func.value.id == 're'
                   and n.func.attr in ('match','search') for n in ast.walk(body)):
                out.append(finding(('B36',), node.lineno,
                                   'body matches "re.(match|search)" and node=loop and not else_branch'))
    return out


def spec_authorship(record, event, cfg):
    if event.get('run') != 'git log base..HEAD':
        return []
    out = []
    for commit in event.get('commits', ()):
        if (str(commit.get('author','')) in cfg.get('named_sets',{}).get('MODEL',())
                or any(matches(cfg, 'MODEL', str(commit.get(k, ''))) for k in ('trailers','message'))):
            out.append(finding(('A13','E3'), commit.get('sha',''),
                               '(author in MODEL or trailers matches MODEL or message matches MODEL) and run="git log base..HEAD"'))
    return out


def spec_terms(record, event, cfg):
    rows = list(event.get('terms', ()))
    if pre(event) and event.get('tool_name') in ('Write', 'Edit'):
        columns = None
        for line in content(event).splitlines():
            if not line.strip().startswith('|'):
                columns = None
                continue
            cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
            if 'check' in cells and ('rule' in cells or 'term' in cells):
                columns = cells
            elif columns and len(cells) == len(columns) and not all(
                    re.fullmatch(r'[: -]+', cell) for cell in cells):
                row = dict(zip(columns, cells))
                rows.append(dict(term=row.get('term', row.get('rule')), check=row['check']))
    return [finding(('B7',), row.get('term',''), 'a TERMS row with check column empty')
            for row in rows if row.get('check') == '']


def spec_write(record, event, cfg):
    if not pre(event) or event.get('tool_name') not in ('Write','Edit'):
        return []
    ti = args(event);text = content(event);path = str(ti.get('file_path',ti.get('path','')))
    out = []
    test = matches(cfg, 'TEST_PATH', path)
    from makoto2 import family_switch
    adapted={'event':'Pre','tool':event.get('tool_name'),'path':path,'content':text}
    if any(family_switch.switch_write(adapted,pattern) for pattern in cfg.get('named_sets',{}).get('TEST_PATH',())):
        out.append(finding(('B2','B5','B20'),path,'not args.content matches "\\b(assert|raise|expect)" and path matches TEST_PATH', 'SPEC.write'))
    if matches(cfg,'WAIVER',text) and not re.search(r'\b(until|expires|remove by)\b',text):
        out.append(finding(('B9',),path,'args.content matches WAIVER and not args.content matches "\\b(until|expires|remove by)\\b"','SPEC.write'))
    if test and re.search(r'assert\s+len\(.*\)\s*<=?\s*\d+',text):
        out.append(finding(('B23',),path,'args.content matches "assert\\s+len\\(.*\\)\\s*<=?\\s*\\d+" and path matches TEST_PATH','SPEC.write'))
    if matches(cfg,'SUPPRESS',text) and not re.search(r'ADR-\d+',text):
        out.append(finding(('B35',),path,'args.content matches SUPPRESS and not args.content matches "ADR-\\d+"','SPEC.write'))
    old = str(ti.get('old',ti.get('old_string','')))
    new = str(ti.get('new',ti.get('new_string','')))
    if event.get('tool_name') == 'Edit' and test and re.search('==',old) and re.search(r'(<=|>=|\bin\b)',new):
        out.append(finding(('C6',),path,'args.new matches "(<=|>=|\\bin\\b)" and args.old matches "==" and path matches TEST_PATH','SPEC.write'))
    return out


def spec_launch(record, event, cfg):
    if event.get('hook_event_name') != 'Launch':
        return []
    settings = event.get('settings', cfg.get('settings',{}))
    plugin = cfg.get('named_sets',{}).get('PLUGIN')
    # An undefined PLUGIN set cannot establish "not tree.PLUGIN.exists".
    missing = bool(plugin) and not all((Path(event.get('cwd') or '.')/p).exists() for p in plugin)
    if settings.get('disableAllHooks') is True or settings.get('enabledPlugins',{}).get('makoto') is not True or missing:
        return [finding(('E12',),'launch','settings.disableAllHooks=true or settings.enabledPlugins.makoto!=true or not tree.PLUGIN.exists')]
    return []


def spec_budget(record, event, cfg):
    elapsed,budget = event.get('elapsed'),event.get('budget')
    if (event.get('run') == 'suite' and isinstance(elapsed,(float,int)) and not isinstance(elapsed,bool)
            and isinstance(budget,(float,int)) and not isinstance(budget,bool) and elapsed >= budget):
        return [finding(('E11',),'suite','elapsed>=budget and run=suite')]
    return []


class Claim(NamedTuple):
    kind: str
    subject: str
    names: bool
    falsifier: bool


# A single fixed word table; no thresholds or semantic classifier.
CLAIM_WORDS = {'pass':('pass','passed','passes','green','success'), 'clean':('clean',),
               'absent':('absent','missing','none'), 'done':('done','fixed','finished','complete','completed','ready'),
               'shipped':('shipped','pushed','landed','merged'), 'running':('running',),
               'count':('failed','failures','passed'), 'plan':('plan','planned'),
               'retracted':('retracted',), 'helps':('helps',), 'cannot':('cannot',"can't")}


def claims(text, record):
    keys = verifier_keys(record)
    identities = set()
    for o in record.obs:
        identities.update(re.findall(r'\b(?:FAIL(?:ED)?|ERROR)\s+([\w./:\[\]-]+)',o.output))
    result=[]
    for sentence in re.split(r'(?<=[.!?])\s+|\n|\s+[-—–]+\s+|;|,?\s+but\s+|,\s+(?=although\b)',str(text or '')):
        if sentence.rstrip().endswith('?'):
            result.append(Claim('question','',False,False));continue
        quoted = re.findall(r'`([^`]+)`',sentence)
        paths = re.findall(r'(?:[\w./-]+/)*[\w.-]+\.[A-Za-z][\w.-]*',sentence)
        # Subject is a complete quoted command/path, otherwise the named path or
        # the text beside the fixed claim word. No arbitrary word-window cutoff.
        names = bool(identities) and all(identity in str(text) or identity.rsplit('::',1)[-1] in str(text) for identity in identities)
        falsifier = bool(re.search(r'\bfalsifier\s*:',str(text),re.I) and
                         (re.findall(r'`([^`]+)`',str(text)) or re.findall(r'[\w/-]+\.[A-Za-z]+',str(text))))
        falsifier = falsifier or any(command in str(text) for command in keys)
        for kind,words in CLAIM_WORDS.items():
            rx = r'\b(?:'+ '|'.join(map(re.escape,words))+r')\b'
            assertion = re.sub(r'"[^"\n]*"|“[^”\n]*”', lambda m: ' ' * len(m.group()), sentence)
            match = re.search(rx,assertion,re.I)
            if (not match or re.search(r'\b(?:not|never|no)\s*$',sentence[:match.start()],re.I)
                    or re.match(r'\s*(?:although|though|while)\b', sentence, re.I)):
                continue
            if (kind == 'shipped' and re.search(r'\b(?:the|a|an|this|that|our|your|its)\s*$',
                                               sentence[:match.start()], re.I)
                    and re.match(r'\s+\w', sentence[match.end():])):
                continue
            if kind=='count' and not re.search(r'\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b',sentence,re.I):continue
            if kind=='pass' and re.search(r'\b\d+\s+passed\b',sentence):continue
            before=sentence[:match.start()].strip(' :.,');after=sentence[match.end():].strip(' :.,')
            commands=[str(args(e).get('command','')) for e in history(record) if args(e).get('command') and str(args(e)['command']) in sentence]
            subject=(quoted[0] if quoted else paths[0].rstrip('.') if paths else commands[0] if commands else (after or before) if kind in ('plan','retracted') else before if kind == 'pass' else '')
            result.append(Claim(kind,subject,names,falsifier))
    return result


def read_claims(record,event):
    explicit=event.get('claim')
    if not isinstance(explicit,dict):
        from makoto2 import observed
        return [c._asdict() for c in claims(observed.text_of(event),record)]
    claim=dict(explicit)
    if 'falsifier' not in claim:
        subject=claim.get('subject')
        claim['falsifier']=bool(subject and subject in verifier_keys(record))
    return [claim]


def spec_claim(record, event, cfg):
    out=[];ti=args(event)
    dispatch=cfg.get('settings',{}).get('makoto',{}).get('dispatch') is True
    if pre(event) and event.get('tool_name')=='Agent' and dispatch:
        prompt=str(ti.get('prompt',''))
        if not all(re.search(r'(?m)^'+label+':',prompt) for label in ('READ','WRITE','ACCEPTANCE')):
            out.append(finding(('I1',),'brief','not (args.prompt matches "(?m)^READ:" and args.prompt matches "(?m)^WRITE:" and args.prompt matches "(?m)^ACCEPTANCE:")','R04'))
    report = stop(event) or (pre(event) and event.get('tool_name') in ('Write','Edit')
                            and not str(ti.get('file_path','')).endswith('.py'))
    if not report:return out
    raw=history(record)
    from makoto2 import family_switch,family_lineage,family_other,observed
    boundary = (getattr(record, 'turn_start', 0) or 0) - 1
    last_edit = max((i for i,e in enumerate(raw) if settled(e) and e.get('tool_name') in ('Write','Edit','MultiEdit','NotebookEdit')), default=-1)
    latest = {}
    for e in raw[boundary+1:]:
        if settled(e) and e.get('tool_name') == 'Bash':
            latest[args(e).get('command','')] = exit_of(e)
    commands = {args(e).get('command') for e in raw if settled(e) and e.get('tool_name') == 'Bash'}
    for value in read_claims(record,event):
        kind, subject = value.get('kind'), value.get('subject','')
        if not stop(event) and kind != 'count':
            continue
        runs = [e for e in raw[last_edit+1:] if settled(e)
                and e.get('tool_name') == 'Bash'
                and (subject not in commands or args(e).get('command') == subject)]
        # A scoped report can cite one successful part while naming a different
        # failed part. A literal subject in the run's output binds that scope.
        scoped = [e for e in runs if subject and subject.lower() in
                  observed._flatten(e.get('tool_response')).lower()]
        if subject not in commands and scoped:
            runs = scoped
        if kind == 'pass' and (not runs or exit_of(runs[-1]) != 0):
            out.append(finding(('A7','C3'),subject,'latest settled run after the last edit is not successful','R11'))
        if kind == 'shipped' and not shipping_observed(record):
            out.append(finding(('C10',),subject,'no successful shipping observation','R11'))
        if kind == 'count' and not value.get('names') and any(code not in (None,0) for code in latest.values()):
            out.append(finding(('C12',),subject,'latest settled subject result is failure','R11'))
    return out


def spec_repeat(record, event, cfg):
    if not pre(event) or event.get('tool_name')!='Bash':return []
    command=args(event).get('command');raw=history(record)
    out=[]
    for success,entries in ((True,('A11',)),(False,('E5','E10'))):
        if success and not re.search('>>',str(command)):continue
        prior=[i for i,e in enumerate(raw) if settled(e) and e.get('tool_name')=='Bash'
               and args(e).get('command')==command and exit_of(e) is not None
               and (exit_of(e)==0)==success]
        boundary = max((i for i,e in enumerate(raw) if args(e).get('command')==command),default=-1)
        if prior and not any(e.get('tool_name') in ('Write','Edit') for e in raw[boundary+1:]):
            out.append(finding(entries,command,'seen(args.command=$args.command and exit'+('=0' if success else '!=0')+') and unseen_since(tool in {Write,Edit}, args.command=$args.command)','R13'))
    return out


def spec_history(record, event, cfg):
    raw=history(record);keys=verifier_keys(record);out=[]
    if pre(event) and event.get('tool_name')=='Agent':
        prior=[i for i,e in enumerate(raw) if e.get('tool_name')=='Agent' and args(e).get('prompt')==args(event).get('prompt')]
        # unseen_since(verifier, tool=Agent): boundary is the last Agent, even a
        # different prompt. seen(prompt=current) is an independent conjunct.
        boundary=max((i for i,e in enumerate(raw) if e.get('tool_name')=='Agent'),default=-1)
        if prior and not any(is_verifier(e,keys) for e in raw[boundary+1:]):
            out.append(finding(('E13',),args(event).get('prompt',''),'seen(tool=Agent and args.prompt=$args.prompt) and unseen_since(verifier, tool=Agent)'))
    if not stop(event):return out
    current=claims(event.get('last_assistant_message',''),record)
    earlier=[c for e in raw if e.get('hook_event_name')=='Stop' for c in claims(e.get('last_assistant_message',''),record)]
    # A request for a plan is distinguishable by an explicit user instruction.
    users = [e.get('prompt','') for e in raw if e.get('hook_event_name') == 'UserPromptSubmit']
    if re.match(r'(?i)^\s*(?:my |the )?plan\s*:', event.get('last_assistant_message','')) and not any(re.search(r'(?i)\bplan\b',u) for u in users):
        out.append(finding(('G2',),'plan','explicit plan without user request'))
    boundary=max((i for i,e in enumerate(raw) if e.get('hook_event_name')=='UserPromptSubmit'),default=-1)
    if any(c.kind=='cannot' for c in current) and not any(
            e.get('hook_event_name')=='PreToolUse' or settled(e) for e in raw[boundary+1:]):
        out.append(finding(('G5',),'cannot','claim.kind=cannot and unseen_since(event=Pre, event=User)'))
    return out


def findings(record, event, cfg):
    """Native events and settled gate output supply the held-definition reading."""
    checks = (spec_tree, spec_write, spec_terms, spec_claim, spec_repeat, spec_history)
    for check in checks:
        yield from check(record, event, cfg)
    from makoto2.family_other import _facts
    for facts in _facts(record):
        for check in (spec_authorship, spec_terms, spec_launch, spec_budget):
            yield from check(record, dict(facts, cwd=facts.get('cwd', event.get('cwd', ''))), cfg)


def evaluate(record, event, cfg):
    return list(findings(record, event, cfg))


def shipping_observed(record):
    from makoto2 import observed
    return any(not o.failed and o.exit in (None, 0) and (o.tool == 'Bash' and o.exit == 0 and any(
        tuple(observed._effective_argv(argv)[:2]) == ('git','push')
        for argv,_ in observed._segments(o.input.get('command',''))) or
        o.tool.rsplit('__',1)[-1] in ('push_files','create_or_update_file','merge_pull_request'))
        for o in record.obs)
