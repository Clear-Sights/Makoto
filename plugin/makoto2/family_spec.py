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

FUNCTIONS = dict.fromkeys(('A3','A4','B36'), 'spec_tree')
FUNCTIONS.update(dict.fromkeys(('A13','E3'), 'spec_authorship'))
FUNCTIONS.update(B7='spec_terms')
FUNCTIONS.update(dict.fromkeys(('B2','B9','B23','B35','C6','E7'), 'spec_write'))
FUNCTIONS.update(E12='spec_launch', E11='spec_budget', A2='spec_refs')
FUNCTIONS.update(dict.fromkeys(('E13','G2','G5','D13'), 'spec_history'))
FUNCTIONS.update(dict.fromkeys(('A11','E5','E10'), 'spec_repeat'))
FUNCTIONS.update(dict.fromkeys(('A7','C2','C7','C10','C12','I1'), 'spec_claim'))


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
    return observed._exit_of(response, observed._flatten(response))


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
            if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
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
    return [finding(('B7',), row.get('term',''), 'a TERMS row with check column empty')
            for row in event.get('terms', ()) if row.get('check') == '']


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
    if re.search(r'if\s+os\.environ',text):
        out.append(finding(('E7',),path,'args.content matches "if\\s+os\\.environ"','SPEC.write'))
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
CLAIM_WORDS = {'pass':('pass','passed','green','success'), 'clean':('clean',),
               'absent':('absent','missing','none'), 'done':('done','fixed','finished','complete','completed','ready'),
               'shipped':('shipped','pushed','landed','merged'), 'running':('running',),
               'count':('failed','failures','passed'), 'plan':('plan','planned'),
               'retracted':('retracted',), 'cannot':('cannot',"can't")}


def claims(text, record):
    keys = verifier_keys(record)
    identities = set()
    for o in record.obs:
        identities.update(re.findall(r'\b(?:FAILED|ERROR)\s+([\w./:\[\]-]+)',o.output))
    result=[]
    for sentence in re.split(r'(?<=[.!?])\s+|\n',str(text or '')):
        if sentence.rstrip().endswith('?'):
            result.append(Claim('question','',False,False));continue
        quoted = re.findall(r'`([^`]+)`',sentence)
        paths = re.findall(r'(?:[\w./-]+/)*[\w.-]+\.[A-Za-z][\w.-]*',sentence)
        # Subject is a complete quoted command/path, otherwise the named path or
        # the text beside the fixed claim word. No arbitrary word-window cutoff.
        names = any(identity in str(text) or identity.rsplit('::',1)[-1] in str(text) for identity in identities)
        falsifier = bool(re.search(r'\bfalsifier\s*:',str(text),re.I) and
                         (re.findall(r'`([^`]+)`',str(text)) or re.findall(r'[\w/-]+\.[A-Za-z]+',str(text))))
        falsifier = falsifier or any(command in str(text) for command in keys)
        for kind,words in CLAIM_WORDS.items():
            rx = r'\b(?:'+ '|'.join(map(re.escape,words))+r')\b'
            match = re.search(rx,sentence,re.I)
            if not match or re.search(r'\b(?:not|never|no)\s*$',sentence[:match.start()],re.I):
                continue
            if kind=='count' and not re.search(r'\b\d+\b',sentence):continue
            if kind=='pass' and re.search(r'\b\d+\s+passed\b',sentence):continue
            before=sentence[:match.start()].strip(' :.,');after=sentence[match.end():].strip(' :.,')
            commands=[str(args(e).get('command','')) for e in history(record) if args(e).get('command') and str(args(e)['command']) in sentence]
            subject=(quoted[0] if quoted else paths[0].rstrip('.') if paths else commands[0] if commands else '')
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
    if not stop(event):return out
    raw=history(record)
    from makoto2 import family_switch,family_lineage,family_other,observed
    observations=[{'command':o.input.get('command',''),'exit':o.exit} for o in record.obs]
    for value in read_claims(record,event):
        claim=Claim(value.get('kind',''),value.get('subject',''),value.get('names',False),bool(value.get('falsifier')))
        if claim.subject and family_switch.switch_pass({'event':'Stop','claim':value},observations):
            out.append(finding(('A7','C3'),claim.subject,'claim.kind=pass and not seen(exit=0 and args.command matches $claim.subject)','R11'))
        if claim.kind in ('clean','absent') and family_lineage.lineage_absence(record,event,observed):
            out.append(finding(('C2','B32'),claim.subject,'claim.kind in {clean,absent} and not claim.falsifier','R05'))
        if claim.kind=='done' and any(entry=='D1' and subject==claim.subject for entry,subject in family_other.other_claim(record,event,observed,cfg.get('dispatch',False))):
            out.append(finding(('C7','D1'),claim.subject,'claim.kind=done and not tree.$claim.subject.exists','R11'))
        if claim.kind=='shipped' and not any(settled(e) and exit_of(e)==0 and re.search(r'git\s+push',str(args(e).get('command',''))) for e in raw):
            out.append(finding(('C10',),claim.subject,'claim.kind=shipped and not seen(args.command matches "git\\s+push" and exit=0)','R11'))
        if claim.kind=='count' and not claim.names and verifier_keys(record):
            out.append(finding(('C12',),claim.subject,'claim.kind=count and not claim.names and seen(verifier and exit!=0)','R11'))
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
    if any(c.kind=='plan' for c in current) and not any(c.kind=='question' for c in earlier):
        out.append(finding(('G2',),'plan','claim.kind=plan and not seen(claim.kind=question)'))
    boundary=max((i for i,e in enumerate(raw) if e.get('hook_event_name')=='UserPromptSubmit'),default=-1)
    if any(c.kind=='cannot' for c in current) and not any(e.get('hook_event_name')=='PreToolUse' for e in raw[boundary+1:]):
        out.append(finding(('G5',),'cannot','claim.kind=cannot and unseen_since(event=Pre, event=User)'))
    planned={c.subject for c in earlier if c.kind=='plan'}
    closed={c.subject for c in earlier if c.kind in ('done','retracted')}
    for item in sorted(planned-closed):
        out.append(finding(('D13','F8'),item,'not seen(claim.kind in {done,retracted} and claim.subject=$item) and seen(claim.kind=plan and claim.subject=$item)'))
    return out


def spec_refs(record,event,cfg):
    from makoto2 import observed, family_lineage
    if not (pre(event) or stop(event)):return []
    return [finding(('A2','G1','H1','H4','H5'), name,
                    'refs(output)-source.read!={} -- source: REGISTRY-v9.md:79,543,761,793,803','R08')
            for name in family_lineage.lineage_refs(record,event,observed)]


def evaluate(record,event,cfg):
    return [f for fn in dict.fromkeys(FUNCTIONS.values()) for f in globals()[fn](record,event,cfg)]
