"""Query representation experiment. No production edits or golden changes.
Paired full channel capture from one LanceDB version. Persist every query.
"""
import sys,json,hashlib,re,statistics,time
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import lancedb
import vault_search_hardened as h
from path_matching import matches_expected
STOP=h.base.STOP | {'siapa','gimana','itu','ini','apakah','does','do','did','can','could','would','should','please','explain','tell','me','about'}
def normalize(q):
    parts=re.findall(r'[\w]+(?:[.-][\w]+)*',q.lower())
    return ' '.join(p for p in parts if p not in STOP) or q
if __name__=='__main__':
 g=ROOT/'golden_queries.json';sha=hashlib.sha256(g.read_bytes()).hexdigest()
 table=lancedb.connect(h.base._cfg()['db_path']).open_table('vault_chunks');version=table.version
 stamp=datetime.now().strftime('%Y%m%d_%H%M%S');out=ROOT/f'normalized_capture_{stamp}.jsonl'
 rows=[]
 with out.open('x') as f:
  for q in json.loads(g.read_text())['queries']:
   if q['type']=='counter' or h.metadata_intent(q['query']) or re.search(r'\blessons?[- ]learned\b',q['query']):continue
   text=q['query'];clean=normalize(text)
   v=table.search(h.embed(text)).limit(200).to_list()
   raw=table.search(text,query_type='fts').limit(200).to_list()
   cleanrows=table.search(clean,query_type='fts').limit(200).to_list()
   cv=table.search(h.embed(clean)).limit(200).to_list() if text!=clean else v
   item={**q,'normalized':clean,'raw_fts':raw,'clean_fts':cleanrows,'vector':v,'clean_vector':cv,'variants':{}}
   for name,fts,vec in [('baseline',raw,v),('clean_fts',cleanrows,v),('clean_both',cleanrows,cv)]:
    channels=[]
    for strategy,weight,chunk,key,dist in [('fts',.4,fts,'_score',False),('vector',.6,vec,'_distance',True)]:
     rr=h.base.unique_rows(chunk,key,dist);rr={s:d for s,d in rr.items() if Path(s).is_file() and Path(s).resolve().is_relative_to(h.base._cfg()['vault_root'])};channels.append((strategy,weight,rr))
    ranked=h.base.fuse_rankers(channels,text)
    rank=next((i for i,r in enumerate(ranked[:15],1) if any(matches_expected(r['source'],e,'../wiki') for e in q['expected'])),None)
    item['variants'][name]={'rank':rank,'top5':[r['source'] for r in ranked[:5]]}
   f.write(json.dumps(item)+'\n');f.flush();rows.append(item)
 assert len(rows)==42
 for name in ['baseline','clean_fts','clean_both']:
  ranks=[x['variants'][name]['rank'] for x in rows]
  print(name,{'n':len(ranks),'hit1':sum(x==1 for x in ranks)/len(ranks),'hit3':sum(x is not None and x<=3 for x in ranks)/len(ranks),'hit5':sum(x is not None and x<=5 for x in ranks)/len(ranks),'mrr':statistics.mean(1/x if x else 0 for x in ranks)})
  print('CHANGES',[(x['id'],x['variants']['baseline']['rank'],x['variants'][name]['rank']) for x in rows if x['variants']['baseline']['rank']!=x['variants'][name]['rank']])
 assert table.version==version and hashlib.sha256(g.read_bytes()).hexdigest()==sha
 print('INDEX',version,'LABEL_HASH',sha,'ARTIFACT',out)
