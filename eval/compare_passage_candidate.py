"""Compare passage/identifier reranking on the same frozen 42 retrieval queries.
Baseline comes from the actual hardened search function with replayed I/O;
chunks are the raw channel rows captured for those identical queries.
No production wiring, no label changes, no network.
"""
import hashlib
import inspect
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import vault_search_hardened as h
import passage_reranker_candidate as pr
from path_matching import matches_expected

CAP = Path('/tmp/rag_ab_capture.json')
capture = json.loads(CAP.read_text())
golden = ROOT / 'golden_queries.json'
assert capture['golden_sha256'] == hashlib.sha256(golden.read_bytes()).hexdigest()
modules = [h, h.base, pr]
source = inspect.getsource(h.base.fuse_rankers)
assert source.count('weight/(60+rank)') == 1  # live baseline unchanged

class ReplayQuery:
    def __init__(self, rows): self.rows = rows; self.n = len(rows)
    def limit(self, n): self.n = n; return self
    def to_list(self): return [dict(r) for r in self.rows[:self.n]]

class ReplayDB:
    def __init__(self, q): self.q = q
    def open_table(self, name):
        assert name == 'vault_chunks'; return self
    def search(self, query, query_type=None):
        if query_type == 'fts':
            assert query == self.q['query']; return ReplayQuery(self.q['fts'])
        assert query == [0.0]; return ReplayQuery(self.q['vector'])

results = []
for q in capture['queries']:
    if q['type'] == 'counter' or h.metadata_intent(q['query']) or re.search(r'\blessons?[- ]learned\b', q['query']):
        continue
    with patch('lancedb.connect', return_value=ReplayDB(q)), patch.object(h, 'embed', return_value=[0.0]):
        baseline = h.search_vault(q['query'], top_k=15, strict=True)
    chunks = q['fts'] + q['vector']
    item = {'id': q['id'], 'type': q['type'], 'query': q['query'], 'variants': {'baseline': {'rank': next((i for i, r in enumerate(baseline, 1) if any(matches_expected(r['source'], e, '../wiki') for e in q['expected'])), None)}}}
    for mode in ('identifier', 'passage', 'combined'):
        t0 = time.perf_counter()
        rows = pr.rerank(q['query'], baseline, chunks, mode)
        ms = (time.perf_counter()-t0)*1000
        rank = next((i for i, r in enumerate(rows, 1) if any(matches_expected(r['source'], e, '../wiki') for e in q['expected'])), None)
        item['variants'][mode] = {'rank': rank, 'ms': round(ms, 2)}
    results.append(item)
assert len(results) == 42, len(results)
summary = {}
for name in ('baseline', 'identifier', 'passage', 'combined'):
    ranks = [r['variants'][name]['rank'] for r in results]
    summary[name] = {'n': len(ranks), 'hit1': round(sum(r == 1 for r in ranks)/len(ranks), 4), 'hit5': round(sum(r is not None and r <= 5 for r in ranks)/len(ranks), 4), 'mrr15': round(statistics.mean(1/r if r else 0 for r in ranks), 4)}
    print(name, json.dumps(summary[name]))
    if name != 'baseline':
        print('CHANGES', [(r['id'], r['variants']['baseline']['rank'], r['variants'][name]['rank']) for r in results if r['variants']['baseline']['rank'] != r['variants'][name]['rank']])
ms = [r['variants'][m]['ms'] for r in results for m in ('identifier', 'passage', 'combined')]
print('RERANK_OVERHEAD_MS p50', round(statistics.median(ms), 2), 'p95', round(sorted(ms)[int(.95*len(ms))-1], 2))
hashes = {str(Path(m.__file__)): hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in modules}
for path, digest in hashes.items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
assert hashlib.sha256(golden.read_bytes()).hexdigest() == capture['golden_sha256']
p = ROOT / ('passage_compare_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
with p.open('x') as f:
    json.dump({'scope': 'frozen replay, actual search baseline, experimental reranker; NOT live', 'capture_sha256': hashlib.sha256(CAP.read_bytes()).hexdigest(), 'source_hashes': hashes, 'golden_sha256': capture['golden_sha256'], 'summary': summary, 'queries': results}, f, indent=2)
print('HASHES_UNCHANGED')
print('ARTIFACT', p)
