#!/usr/bin/env python3
"""Runnable source-scenario coverage and removal witness in a standalone skill folder."""
import json,re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=json.loads((root/'references/WITNESSES.json').read_text())
if len(sys.argv)!=2: raise SystemExit('usage: witness.py /path/to/SKILL.md')
path=Path(sys.argv[1])
text=path.read_text();parts=re.split(r'<!-- rule_id: ([A-Z]+\d+) -->',text);cards={parts[i]:parts[i+1] for i in range(1,len(parts),2)};errors=[]
for rid,r in spec['rules'].items():
    clauses=[json.loads(c) for c in re.findall(r'<!-- contract: (.*?) -->',cards.get(rid,''))]
    actions=set().union(*(set(c.get('actions',[])) for c in clauses));classes=set().union(*(set(c.get('classes',[])) for c in clauses));forbidden=set().union(*(set(c.get('forbidden',[])) for c in clauses))
    if set(r['actions'])-actions or set(r['classes'])-classes or set(r['forbidden'])-forbidden or not any(c.get('role')=='Evidence' and c.get('refs') for c in clauses):errors.append(rid)
print(json.dumps({'status':'fail' if errors else 'pass','rules':len(spec['rules']),'errors':errors,'efficacy':'unknown'},sort_keys=True));sys.exit(bool(errors))
