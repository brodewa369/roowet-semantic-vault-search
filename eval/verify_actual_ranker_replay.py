"""Exercise the actual hardened search function with frozen channel responses.
Only database and embedding I/O are replayed; ranking, dedup, source filters,
validation and truncation execute normally. This is NOT a live MCP benchmark.
"""
import hashlib
import inspect
import json
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
import vault_search_hardened as h
from path_matching import matches_expected

CAP = Path('/tmp/rag_ab_capture.json')
capture = json.loads(CAP.read_text())
golden = ROOT / 'golden_queries.json'
assert hashlib.sha256(golden.read_bytes()).hexdigest() == capture['golden_sha256']
hashes = {str(Path(m.__file__)): hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (h, h.base)}
source = inspect.getsource(h.base.fuse_rankers)
assert source.count('weight/(60+rank)') == 1
namespace = dict(vars(h.base))
exec(source.replace('weight/(60+rank)', 'weight/(20+rank)'), namespace)
rrf20 = namespace['fuse_rankers']
baseline = h.base.fuse_rankers

class ReplayQuery:
    def __init__(self, rows):
        self.rows = rows
        self.n = len(rows)
    def limit(self, n):
        self.n = n
        return self
    def to_list(self):
        return [dict(row) for row in self.rows[:self.n]]

class ReplayDB:
    def __init__(self, q):
        self.q = q
    def open_table(self, name):
        assert name == 'vault_chunks'
        return self
    def search(self, query, query_type=None):
        if query_type == 'fts':
            assert query == self.q['query']
            return ReplayQuery(self.q['fts'])
        assert query == [0.0]
        return ReplayQuery(self.q['vector'])

results = []
for q in capture['queries']:
    if q['type'] == 'counter' or h.metadata_intent(q['query']) or re.search(r'\blessons?[- ]learned\b', q['query']):
        continue
    item = {'id': q['id'], 'query': q['query'], 'expected': q['expected'], 'variants': {}}
    for label, ranker in [('baseline', baseline), ('rrf20', rrf20)]:
        with patch('lancedb.connect', return_value=ReplayDB(q)), patch.object(h, 'embed', return_value=[0.0]), patch.object(h.base, 'fuse_rankers', ranker):
            rows = h.search_vault(q['query'], top_k=15, strict=True)
        rank = next((i for i, row in enumerate(rows, 1) if any(matches_expected(row['source'], e, '../wiki') for e in q['expected'])), None)
        item['variants'][label] = {'rank': rank, 'results': rows}
    results.append(item)
assert len(results) == 42, len(results)
summary = {}
for name in ('baseline', 'rrf20'):
    ranks = [r['variants'][name]['rank'] for r in results]
    summary[name] = {'n': len(ranks), 'hit1': sum(r == 1 for r in ranks)/len(ranks), 'hit5': sum(r is not None and r <= 5 for r in ranks)/len(ranks), 'mrr15': statistics.mean(1/r if r else 0 for r in ranks)}
    print(name, json.dumps(summary[name]))
print('CHANGES', [(r['id'], r['variants']['baseline']['rank'], r['variants']['rrf20']['rank']) for r in results if r['variants']['baseline']['rank'] != r['variants']['rrf20']['rank']])
for qid in ('q40', 'q42'):
    q = next(q for q in capture['queries'] if q['id'] == qid)
    f = h.base.unique_rows(q['fts'], '_score')
    v = h.base.unique_rows(q['vector'], '_distance', True)
    ranked = baseline([('fts', .4, f), ('vector', .6, v)], q['query'])
    terms = h.base.tokens(q['query'])
    selected = {r['source'] for r in ranked[:2]} | {str(Path('../wiki')/e) for e in q['expected']}
    print('DIAGNOSIS', qid, 'TOKENS', sorted(terms), 'IDENTIFIERS', re.findall(r'\b[\w-]+\.(?:dll|py|js|json|yaml|toml|md)\b', q['query']))
    for s in sorted(selected):
        info = {'source': s, 'exists': Path(s).is_file(), 'inside_root': Path(s).resolve().is_relative_to('../wiki')}
        title = re.sub(r'^\d{4}-\d\d-\d\d-', '', Path(s).stem)
        info['title_multiplier'] = 1+.5*len(terms & h.base.tokens(title))/max(len(terms),1)
        for name, channel in [('fts', f), ('vector', v)]:
            ordered = sorted(channel, key=lambda k: (-channel[k]['score'], k))
            info[name+'_rank'] = ordered.index(s)+1 if s in channel else None
            info[name+'_excerpt'] = channel[s]['text'][:700] if s in channel else None
        print(json.dumps(info))
for path, digest in hashes.items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
assert hashlib.sha256(golden.read_bytes()).hexdigest() == capture['golden_sha256']
p = ROOT / ('actual_ranker_replay_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.json')
with p.open('x') as f:
    json.dump({'scope':'actual search function, replayed I/O, current source filtering; NOT live MCP', 'capture_sha256':hashlib.sha256(CAP.read_bytes()).hexdigest(), 'capture_index_version':capture['table_version'], 'source_hashes':hashes,'golden_sha256':capture['golden_sha256'],'summary':summary,'queries':results}, f, indent=2)
print('SOURCE_AND_LABEL_HASHES_UNCHANGED')
print('ARTIFACT', p)
