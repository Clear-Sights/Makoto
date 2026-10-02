#!/usr/bin/env python3
import json,sys

def check(s):
    kinds={'data_dependency','one_door','resident_fault','inherited_setting','declared_count'}
    unknown='unknown'
    kind=s.get('construction',unknown)
    tier=1 if kind in ('data_dependency','one_door') else (2 if kind in kinds else unknown)
    swale=kind in kinds and s.get('inherited') is True and s.get('maintenance_checked') is True and s.get('omission_test') is True
    counts=s.get('counts',{})
    conserved=counts.get('in')==counts.get('out',0)+counts.get('dropped',0) if all(isinstance(counts.get(k),int) and not isinstance(counts.get(k),bool) and counts[k]>=0 for k in ('in','out','dropped')) else unknown
    return {'schema':1,'tier':tier,'swale':swale,'count_conserved':conserved,'efficacy':unknown}
if __name__=='__main__':print(json.dumps(check(json.load(sys.stdin)),sort_keys=True))
