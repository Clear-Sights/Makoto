#!/usr/bin/env python3
"""Pure admission predicate; caller must verify/consume within its effect transaction."""
import json,sys,datetime

def check(r,c,used=()):
    faults=[]
    for k in ('subject','effect','criteria','evidence','performer','verifier','receipt_id','observed_at'):
        if not r.get(k):faults.append('missing:'+k)
    for k in ('subject','effect','criteria'):
        if not r.get(k) or r.get(k)!=c.get(k):faults.append('binding:'+k)
    if r.get('receipt_id') in used:faults.append('reused')
    if r.get('verifier')==r.get('performer') or r.get('verifier_authorized') is not True:faults.append('independence')
    evidence=r.get('evidence',[])
    for e in evidence:
        if not isinstance(e,dict) or not e.get('source') or not e.get('digest') or e.get('controlled_by')==r.get('performer') or not e.get('controlled_by'):faults.append('self_report');continue
        actual=c.get('sources',{}).get(e['source'],{})
        if actual.get('digest')!=e['digest']:faults.append('changed_source')
        if actual.get('conditions')!=e.get('conditions') or actual.get('conditions_satisfied') is not True:faults.append('conditions')
        try:
            end=datetime.datetime.fromisoformat(e['valid_through']);now=datetime.datetime.fromisoformat(c['now'])
            if not end.tzinfo or not now.tzinfo or now>end:faults.append('expiry')
        except (KeyError,ValueError,TypeError):faults.append('unknown_validity')
    return {'schema':1,'admission':'deny' if faults else 'admit','faults':sorted(set(faults)),'receipt_id':r.get('receipt_id','unknown'),'scope':'predicate only; effect transition must atomically re-resolve, verify and consume'}
if __name__=='__main__':
    s=json.load(sys.stdin);r=check(s.get('receipt',{}),s.get('current',{}),s.get('used',[]));print(json.dumps(r,sort_keys=True));sys.exit(r['admission']!='admit')
