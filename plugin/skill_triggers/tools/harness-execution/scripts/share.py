#!/usr/bin/env python3
"""C18 numeric readout from settled complete bills; no provider quota inference."""
import json,sys,math

def read(s):
    rows=s.get('bills',[]); good=bool(rows) and s.get('complete') is True
    ids=set();codex=0;total=0
    for r in rows:
        key=r.get('id');n=r.get('total')
        if not key or key in ids or r.get('status')!='known' or r.get('settled') is not True or not isinstance(n,(int,float)) or isinstance(n,bool) or not math.isfinite(n) or n<0 or r.get('family') not in ('codex','other'):good=False;continue
        ids.add(key);total+=n;codex+=n if r['family']=='codex' else 0
    share=codex/total if good and total>0 else 'unknown'
    return {'schema':1,'codex_tokens':codex if good else 'unknown','total_tokens':total if good else 'unknown','share':share,'threshold':0.95,'dispatch':'resume' if isinstance(share,float) and share>=0.95 else 'stop','quota':'awareness:W5; unknown until refreshed authoritative readout','padding_allowed':False}
if __name__=='__main__':print(json.dumps(read(json.load(sys.stdin)),sort_keys=True))
