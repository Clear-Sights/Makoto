#!/usr/bin/env python3
"""Recount shipped historical labels, not a new live experiment."""
from pathlib import Path
import csv,json
p=Path(__file__).resolve().parents[1]/'references/evidence'
def rows(n):return list(csv.DictReader((p/n).open(),delimiter='\t'))
cls=json.loads((p/'CLASSIFICATION.json').read_text());r1=rows('R1.tsv');cost=next(r for r in r1 if r['plant']=='cost');seams=rows('SEAMS.tsv');s27=rows('S27.tsv')
print(json.dumps({'r1_real':sum(r['plant']!='cost' and r['plant'] not in cls['equivalent'] for r in r1),'r1_cells':len(cls['cell_flagged']),'r1_combined':len(set(cls['cell_flagged'])|set(cls['reader_flagged'])),'reader_tokens':sum(int(cost[k].split()[0].replace(',','')) for k in ('opus reader','sonnet reader','haiku reader')),'seams':len(seams),'holes':sum(int(r['holes']) for r in seams),'s27_plants':sum(r['plant'] not in ('base','cost') for r in s27),'scope':'historical authored labels re-counted; live efficacy unknown'},sort_keys=True))
