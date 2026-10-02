#!/usr/bin/env python3
"""Validate recorded dispatch constraints; classify controls without claiming efficacy."""
import json,sys

def check(s):
    faults=[]
    jobs=s.get('jobs',[])
    for j in jobs:
        for k in ('reads','writes','acceptance','expected','return_limit','facts'):
            if not j.get(k):faults.append('missing_'+k)
        if j.get('changed_retry') is False:faults.append('unchanged_retry')
        if j.get('context_canary') and j.get('returned_canary')!=j['context_canary']:faults.append('unread_context')
    for i,a in enumerate(jobs):
        for b in jobs[i+1:]:
            if set(a.get('writes',[]))&set(b.get('writes',[])):faults.append('shared_write')
    for k in ('cache_prefix_stable','append_only','tool_set_stable'):
        if s.get(k) is False:faults.append(k)
    return {'schema':1,'status':'fail' if faults else ('pass' if jobs else 'not_evaluable'),'faults':sorted(set(faults))}
if __name__=='__main__':
    result=check(json.load(sys.stdin));print(json.dumps(result,sort_keys=True));sys.exit(result['status']!='pass')
