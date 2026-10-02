#!/usr/bin/env python3
import json,sys

def read(s):
    before=s.get('before',{});after=s.get('after',{});keys=('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens')
    comparable=s.get('same_task') is True and s.get('same_conditions') is True and all(isinstance(v.get(k),int) and not isinstance(v.get(k),bool) and v[k]>=0 for v in (before,after) for k in keys)
    savings=comparable and s.get('done_pass') is True and all(after[k]<=before[k] for k in keys) and any(after[k]<before[k] for k in keys)
    return {'schema':1,'comparable':comparable,'savings':savings if comparable else 'unknown','delta':{k:after[k]-before[k] for k in keys} if comparable else 'unknown','scope':s.get('scope','unknown')}
if __name__=='__main__':print(json.dumps(read(json.load(sys.stdin)),sort_keys=True))
