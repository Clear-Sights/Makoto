#!/usr/bin/env python3
"""Validate explicit audit receipts; unknown and skipped are never pass."""
import json,sys

def read(s):
    claims=s.get('claims',[]); keys=('subject','revision','input_hashes','argv','expected_exit','actual_exit','source')
    records=[]
    for c in claims:
        known=all(k in c for k in keys) and all(c[k] for k in ('subject','revision','input_hashes','argv','source')) and c.get('ran') is True
        state=('pass' if c['actual_exit']==c['expected_exit'] else 'fail') if known else 'not_evaluable'
        records.append({'id':c.get('id','unknown'),'status':state,'source':c.get('source','unknown')})
    counts={k:sum(r['status']==k for r in records) for k in ('pass','fail','not_evaluable')}
    return {'schema':1,'revision':s.get('revision','unknown'),'claims':records,'counts':counts,'total':len(records),'status':'fail' if counts['fail'] else ('pass' if records and not counts['not_evaluable'] else 'not_evaluable'),'efficacy':'unknown'}
if __name__=='__main__':print(json.dumps(read(json.load(sys.stdin)),sort_keys=True))
