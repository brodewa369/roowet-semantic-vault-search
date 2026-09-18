"""Frozen-candidate diagnosis; no live changes, no label modifications."""
import json,sys,re,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vault_search_candidate as b
import vault_search_hardened as h
from path_matching import matches_expected
root=Path(__file__).parent
cap=Path('/tmp/rag_ab_capture.json'); data=json.loads(cap.read_text())
assert data['golden_sha256']==hashlib.sha256((root/'golden_queries.json').read_bytes()).hexdigest()
out=[]
for q in data['queries']:
 if q['type']=='counter' or h.metadata_intent(q['query']) or re.search(r'\blessons?[- ]learned\b',q['query']):continue
 f=b.unique_rows(q['fts'],'_score');v=b.unique_rows(q['vector'],'_distance',True)
 ranked=b.fuse_rankers([('fts',.4,f),('vector',.6,v)],q['query'])
 channels={k:[s for s,d in sorted(rows.items(),key=lambda x:(-x[1]['score'],x[0]))] for k,rows in [('fts',f),('vector',v)]}
 match=lambda s,e:matches_expected(s,e,'/home/dxwx/wiki')
 targets=[]
 for e in q['expected']:
  ranks={k:next((i for i,s in enumerate(ss,1) if match(s,e)),None) for k,ss in channels.items()}
  ranks['fused']=next((i for i,r in enumerate(ranked,1) if match(r['source'],e)),None)
  targets.append({'expected':e,**ranks})
 out.append({'id':q['id'],'targets':targets,'rank':next((i for i,r in enumerate(ranked,1) if any(match(r['source'],e) for e in q['expected'])),None)})
n=len(out)
for label,pred in [('raw_union',lambda t:t['fts'] is not None or t['vector'] is not None),('capped_union',lambda t:any(t[k] is not None and t[k]<=60 for k in ['fts','vector'])),('fused_top5',lambda t:t['fused'] is not None and t['fused']<=5)]:
 print(label,'ANY',sum(any(pred(t) for t in q['targets']) for q in out),'/',n,'ALL_LABELS',sum(all(pred(t) for t in q['targets']) for q in out),'/',n)
for q in out:
 if q['rank']!=1:print(json.dumps(q))
p=root/'candidate_ceiling_diagnosis_20260918.json'
with p.open('x') as f:json.dump({'capture_sha256':hashlib.sha256(cap.read_bytes()).hexdigest(),'table_version':data['table_version'],'results':out},f,indent=2)
print('ARTIFACT',p)
