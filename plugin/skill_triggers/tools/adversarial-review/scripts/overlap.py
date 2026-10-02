#!/usr/bin/env python3
"""Compute extensions on a declared corpus; overlap is not duplicate decisions."""
import json,sys,itertools

def check(s):
    extensions={k:set(v) for k,v in s.get('extensions',{}).items()};declared=s.get('relations',{});actual={};faults=[]
    universe=set(s.get('corpus',[]))
    for k,v in extensions.items():
        if not v:faults.append('dead:'+k)
        if v-universe:faults.append('foreign:'+k)
    for a,b in itertools.combinations(sorted(extensions),2):
        x,y=extensions[a],extensions[b]
        relation='equal' if x==y else ('subset' if x<y else ('superset' if x>y else ('overlap' if x&y else 'disjoint')))
        key=a+'|'+b;actual[key]=relation
        if declared.get(key)!=relation:faults.append('relation:'+key)
    if set(declared)!=set(actual):faults.append('relation_inventory')
    return {'schema':1,'status':'fail' if faults else ('pass' if extensions and universe else 'not_evaluable'),'relations':actual,'faults':faults}
if __name__=='__main__':
    r=check(json.load(sys.stdin));print(json.dumps(r,sort_keys=True));sys.exit(r['status']!='pass')
