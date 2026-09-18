#!/usr/bin/env python3
"""eval_50_queries.py — Run 50-query golden set evaluation."""

import json, sys, os, importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hybrid_search
importlib.reload(hybrid_search)
from hybrid_search import search_hybrid

g = json.load(open('golden_queries.json'))
queries = g['queries']

hit1 = hit3 = hit5 = mrr_sum = total = 0
misses = []

for q in queries:
    total += 1
    qid = q['id']
    qtype = q['type']
    qtext = q['query']
    expected = q.get('expected', [])
    
    # Run search
    r = search_hybrid(qtext, top_k=8)
    files = [c['source'].split('/')[-1] for c in r]
    
    # Check rank
    rank = None
    for i, f in enumerate(files):
        for exp in expected:
            exp_name = exp.split('/')[-1]
            if exp_name in f or f in exp_name:
                rank = i + 1
                break
        if rank:
            break
    
    if rank:
        if rank <= 1: hit1 += 1
        if rank <= 3: hit3 += 1
        if rank <= 5: hit5 += 1
        mrr_sum += 1/rank
        status = f"r={rank}"
    else:
        misses.append(qid)
        status = "MISS"
    
    print(f"  {qid} [{qtype:10}] {status:6} :: {qtext[:45]}")

print()
print(f"Golden Set 50 queries:")
print(f"  hit@1 = {hit1/total:.3f} ({hit1}/{total})")
print(f"  hit@3 = {hit3/total:.3f} ({hit3}/{total})")
print(f"  hit@5 = {hit5/total:.3f} ({hit5}/{total})")
print(f"  MRR   = {mrr_sum/total:.3f}")
print(f"  Misses ({len(misses)}): {misses}")
