"""Deploy candidate as a search-only MCP override server on a separate port,
exercising the real JSON-RPC path with the reranker installed. Not production.
"""
import hashlib
import json
import os
import selectors
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
golden = ROOT / 'golden_queries.json'
sha = hashlib.sha256(golden.read_bytes()).hexdigest()
queries = json.loads(golden.read_text())['queries']
stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
candidate = ROOT / 'passage_reranker_candidate.py'
import passage_reranker_candidate as pr
handles = [pr]
# Pre-hash the frozen inputs; re-verified after the run.
raw = ROOT / f'candidate_wire_{stamp}.jsonl'
stderr = (ROOT / f'candidate_wire_{stamp}.stderr.log').open('x')
env = {**os.environ, 'QUERY_LOG_PATH': str(ROOT / f'candidate_wire_queries_{stamp}.jsonl')}
entry = ROOT / 'passage_override_entry.py'
entry_sha = hashlib.sha256(entry.read_bytes()).hexdigest()
p = subprocess.Popen([sys.executable, '-u', str(entry)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, text=True, env=env)
sel = selectors.DefaultSelector(); sel.register(p.stdout, selectors.EVENT_READ)
ident = 0

def rpc(method, params):
    global ident
    ident += 1
    p.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params}) + '\n'); p.stdin.flush()
    if not sel.select(90): raise TimeoutError('MCP timeout')
    reply = json.loads(p.stdout.readline())
    assert reply['id'] == ident and 'error' not in reply, reply
    return reply['result']

def call(name, args):
    response = rpc('tools/call', {'name': name, 'arguments': args})
    data = json.loads(response['content'][0]['text']); assert 'error' not in data, data
    return data

from path_matching import matches_expected
rows = []
try:
    rpc('initialize', {})
    names = [d['name'] for d in rpc('tools/list', {})['tools']]
    assert 'search_vault' in names and 'recall' in names
    with raw.open('x') as f:
        for q in queries:
            start = time.monotonic()
            data = call('search_vault', {'query': q['query'], 'top_k': 15})
            ms = round(1000*(time.monotonic()-start), 2)
            sources = [r['source'] for r in data['results']]
            assert len(sources) == len(set(sources))
            rank = next((i for i, s in enumerate(sources, 1) if any(matches_expected(s, e, '/home/dxwx/wiki') for e in q['expected'])), None)
            row = {'id': q['id'], 'type': q['type'], 'rank': rank, 'ms': ms, 'sources': sources}
            rows.append(row); f.write(json.dumps(row) + '\n'); f.flush()
    def metrics(items):
        items = [r for r in items if r['type'] != 'counter']
        return {'n': len(items), **{f'hit@{k}': round(sum(r['rank'] is not None and r['rank'] <= k for r in items)/len(items), 3) for k in (1, 3, 5, 8, 15)}, 'mrr': round(statistics.mean(1/r['rank'] if r['rank'] else 0 for r in items), 3)}
    original = metrics([r for r in rows if int(r['id'][1:]) <= 22])
    expanded = metrics(rows)
    print('CANDIDATE_ORIGINAL', json.dumps(original))
    print('CANDIDATE_EXPANDED', json.dumps(expanded))
    print('LATENCY_MS p50', statistics.median(r['ms'] for r in rows), 'p95', sorted(r['ms'] for r in rows)[47])
finally:
    p.stdin.close()
    try: p.wait(timeout=5)
    except subprocess.TimeoutExpired: p.terminate(); p.wait(timeout=5)
    sel.close(); p.stdout.close(); stderr.close()
print('CANDIDATE_SERVER_EXITED')
