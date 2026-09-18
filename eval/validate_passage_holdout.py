"""Fresh-query, paired stdio validation; two isolated servers, no live writes.
No tuning from these results. Timing includes full retrieval, not rerank only.
"""
import sys, json, subprocess, selectors, time, hashlib, statistics
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
import lancedb
import vault_search_hardened as h
from path_matching import matches_expected
stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
labels=ROOT/'passage_holdout_20260918.json'
queries=json.loads(labels.read_text())['queries']
files=[labels,ROOT/'passage_reranker_candidate.py',ROOT/'passage_override_entry.py',Path(h.__file__),Path(h.base.__file__),ROOT/'golden_queries.json']
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
def version():return lancedb.connect(h.base._cfg()['db_path']).open_table('vault_chunks').version
v0=version()
processes={};rows=[]
try:
 for name,entry in [('baseline',ROOT.parent/'semantic_vault_entry.py'),('candidate',ROOT/'passage_override_entry.py')]:
  err=(ROOT/f'holdout_{stamp}_{name}.stderr.log').open('x')
  p=subprocess.Popen([sys.executable,'-u',str(entry)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True)
  sel=selectors.DefaultSelector();sel.register(p.stdout,selectors.EVENT_READ)
  processes[name]=(p,sel,err)
 def rpc(name,method,params,ident):
  p,sel,err=processes[name]
  p.stdin.write(json.dumps({'jsonrpc':'2.0','id':ident,'method':method,'params':params})+'\n');p.stdin.flush()
  if not sel.select(90):raise TimeoutError(name)
  line=p.stdout.readline()
  if not line:raise RuntimeError('Server exited; inspect '+err.name)
  r=json.loads(line);assert r.get('id')==ident and 'error' not in r,r
  return r['result']
 for name in processes:rpc(name,'initialize',{},0)
 out=ROOT/f'holdout_wire_{stamp}.jsonl'
 with out.open('x') as f:
  for i,q in enumerate(queries,1):
   order=['baseline','candidate'] if i%2 else ['candidate','baseline']
   for name in order:
    t=time.perf_counter()
    r=rpc(name,'tools/call',{'name':'search_vault','arguments':{'query':q['query'],'top_k':15}},i)
    data=json.loads(r['content'][0]['text']);assert 'error' not in data,data
    rank=next((j for j,row in enumerate(data['results'],1) if any(matches_expected(row['source'],e,'/home/dxwx/wiki') for e in q['expected'])),None)
    item={'id':q['id'],'arm':name,'rank':rank,'ms':round((time.perf_counter()-t)*1000,2),'response':data}
    rows.append(item);f.write(json.dumps(item)+'\n');f.flush()
 summary={}
 for name in processes:
  rs=[r for r in rows if r['arm']==name];n=len(rs)
  summary[name]={'n':n,'hit1':sum(r['rank']==1 for r in rs)/n,'hit5':sum(r['rank'] is not None and r['rank']<=5 for r in rs)/n,'mrr15':statistics.mean(1/r['rank'] if r['rank'] else 0 for r in rs),'p50_ms':statistics.median(r['ms'] for r in rs),'max_ms':max(r['ms'] for r in rs)}
 for q in queries:
  rs={r['arm']:r for r in rows if r['id']==q['id']}
  print(q['id'],rs['baseline']['rank'],'->',rs['candidate']['rank'])
 assert len(rows)==2*len(queries)
 assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==s for p,s in hashes.items())
 v1=version()
 report={'scope':'8 implementer-authored post-freeze paraphrases; NOT independent holdout','summary':summary,'hashes':hashes,'index_versions':[v0,v1],'index_unchanged':v0==v1,'raw':str(out)}
 pth=ROOT/f'holdout_acceptance_{stamp}.json';pth.open('x').write(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2));print('REPORT',pth)
finally:
 for p,sel,err in processes.values():
  p.stdin.close()
  try:p.wait(timeout=5)
  except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=5)
  p.stdout.close();sel.close();err.close()
