#!/usr/bin/env python3
"""Read an explicit settled step record. Never discover a session or infer quota/price."""
import json,sys,datetime,math
U='unknown'
TYPES=('input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens')
def num(v): return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v>=0
def read(record):
    out={'schema':1,'step':record.get('step',U),'start':record.get('start',U),'end':record.get('end',U),'settled':record.get('settled',False),'source':record.get('source',U),'observed_at':record.get('observed_at',U),'coverage':record.get('coverage',U),'messages':U,'tokens':{k:U for k in TYPES},'total':U,'cost':U,'currency':U,'status':'unknown'}
    try:
        start=datetime.datetime.fromisoformat(record['start']); end=datetime.datetime.fromisoformat(record['end'])
        if not start.tzinfo or not end.tzinfo or start>end or record.get('settled') is not True or record.get('complete') is not True or not record.get('source') or not record.get('coverage'): return out
        latest={}
        for r in record.get('messages',[]):
            at=datetime.datetime.fromisoformat(r['at'])
            if not at.tzinfo: return out
            if start<=at<=end:
                key=(r['provider'],r['session'],r['id'])
                if not all(isinstance(k,str) and k for k in key):return out
                latest[key]=r  # final usage per provider/session/message; explicit append order
        aggregate=record.get('aggregate')
        if aggregate is not None:
            if aggregate.get('authoritative') is not True or aggregate.get('start')!=record['start'] or aggregate.get('end')!=record['end']:return out
            usage=aggregate['tokens']; count=aggregate.get('messages',U)
        else:
            if not latest or any(not all(num(r.get('tokens',{}).get(k)) for k in TYPES) for r in latest.values()):return out
            usage={k:sum(r['tokens'][k] for r in latest.values()) for k in TYPES};count=len(latest)
        if not all(num(usage.get(k)) for k in TYPES):return out
        out.update(tokens={k:usage[k] for k in TYPES},total=sum(usage[k] for k in TYPES),messages=count,status='known')
        price=record.get('price',{})
        if price.get('authoritative') is True and price.get('source') and price.get('currency') and all(num(price.get('per_token',{}).get(k)) for k in TYPES):
            out.update(cost=sum(usage[k]*price['per_token'][k] for k in TYPES),currency=price['currency'])
    except (KeyError,TypeError,ValueError,OverflowError): pass
    return out
if __name__=='__main__':
    try: record=json.load(sys.stdin); record=record if isinstance(record,dict) else {}
    except ValueError: record={}
    print(json.dumps(read(record),sort_keys=True,allow_nan=False))
