"""Draw the sample of holds per eval/RULES2.md.

    python3 eval/sample.py results.jsonl sample.json
"""
import json
import random
import sys

SEED, SIZE = 20261106, 60


def main():
    holds = []
    for line in open(sys.argv[1]):
        result = json.loads(line)
        holds += [{'id': result['id'], 'i': row['i'], 'reason': row['reason']} for row in result['rows'] if row['kind'] == 'hold']
    holds.sort(key=lambda h: (h['id'], h['i']))
    sample = random.Random(SEED).sample(holds, SIZE)
    json.dump({'seed': SEED, 'population': len(holds), 'holds': sample}, open(sys.argv[2], 'w'), indent=1)
    print(len(holds), 'holds,', len(sample), 'sampled')


if __name__ == '__main__':
    main()
