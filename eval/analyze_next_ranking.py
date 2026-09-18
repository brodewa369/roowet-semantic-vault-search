"""Read-only, offline ablations; exploratory, not independent validation.
Replays frozen ranker candidates. Does not patch live code or golden labels.
"""
import sys,json,re,statistics,hashlib
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vault_search_hardened as h
from path_matching import matches_expected
root=Path(__file__).resolve().parent
capture=json.loads(Path('/tmp/rag_ab_capture.json').read_text())
golden=root/'golden_queries.json'
assert capture['golden_sha256']==hashlib.sha256(golden.read_bytes()).hexdigest()
results=[]
for q in capture['queries']:
    if h.metadata_intent(q['query']) or re.search(r'\blessons?[- ]learned\b',q['query']):continue
    f=h.base.unique_rows(q['fts'],'_score');v=h.base.unique_rows(q['vector'],'_distance',True)
    ranked=h.base.fuse_rankers([('fts',.4,f),('vector',.6,v)],q['query'])
    raw=q['fts']+q['vector']
    bysource={}
    for row in raw:bysource.setdefault(row['source'],[]).append(row['text'])
    # Explicit technical identifiers must survive tokenization. Presence is boolean,
    # evaluated over all retrieved chunks from a file, not only its retained snippet.
    identifiers=re.findall(r'\b[\w-]+\.(?:dll|py|js|json|yaml|toml|md)\b|\b0x[a-fA-F0-9]{8,}\b',q['query'],re.I)
    terms=h.base.tokens(q['query'])
    def identifier_match(row):
        text='\n'.join(bysource.get(row['source'],[])).lower()
        return all(identifier.lower() in text for identifier in identifiers)
    variants={'baseline':ranked}
    # Sharpen rank separation without altering weights or title bonus.
    for constant in (10, 20):
        fused={}
        for weight,channel in ((.4,f),(.6,v)):
            for pos,(source,row) in enumerate(sorted(channel.items(),key=lambda item:(-item[1]['score'],item[0]))[:60],1):
                if source not in fused:fused[source]={**row,'source':source,'score':0.}
                fused[source]['score']+=weight/(constant+pos)
        for source,row in fused.items():
            title=re.sub(r'^\d{4}-\d\d-\d\d-','',Path(source).stem)
            row['score']*=1+.5*len(terms & h.base.tokens(title))/max(len(terms),1)
        variants[f'rrf_{constant}']=sorted(fused.values(),key=lambda row:(-row['score'],row['source']))
    variants['exact_identifier_priority']=sorted(ranked,key=lambda row:not identifier_match(row)) if identifiers else ranked
    # A deliberately simple global coverage hypothesis to falsify, not a chosen fix.
    variants['content_coverage']=sorted(ranked,key=lambda row:-row['score']*(1+0.5*max((len(terms & h.base.tokens(text))/max(len(terms),1) for text in bysource.get(row['source'],[''])),default=0)))
    out={'id':q['id'],'type':q['type'],'query':q['query'],'identifiers':identifiers,'variants':{}}
    for name,rows in variants.items():
        rank=next((i for i,row in enumerate(rows[:15],1) if any(matches_expected(row['source'],e,'/home/dxwx/wiki') for e in q['expected'])),None)
        out['variants'][name]={'rank':rank,'top5':[r['source'] for r in rows[:5]]}
    results.append(out)
for name in ('baseline','rrf_10','rrf_20','exact_identifier_priority','content_coverage'):
    valid=[r for r in results if r['type']!='counter']
    ranks=[r['variants'][name]['rank'] for r in valid]
    print(name,'n',len(valid),'hit1',round(sum(r==1 for r in ranks)/len(ranks),3),'hit5',round(sum(r is not None and r<=5 for r in ranks)/len(ranks),3),'mrr15',round(statistics.mean(1/r if r else 0 for r in ranks),3))
    if name!='baseline':
        print('CHANGES',[(r['id'],r['variants']['baseline']['rank'],r['variants'][name]['rank']) for r in valid if r['variants']['baseline']['rank']!=r['variants'][name]['rank']])
p=root/('next_ranking_ablation_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
with p.open('x') as file:json.dump({'capture_table_version':capture['table_version'],'golden_sha256':capture['golden_sha256'],'queries':results},file,indent=2)
print('EVIDENCE',p)
