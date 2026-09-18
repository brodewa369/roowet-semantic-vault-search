#!/usr/bin/env python3
"""Experimental file-level hybrid retrieval; no benchmark labels in this module.
RRF combines independent rankers; filename overlap is a bounded relevance signal.
Metadata filters inspect note frontmatter, never indexing timestamps.
"""
import os
import re
import logging
from pathlib import Path
from datetime import datetime, timedelta
import yaml

log = logging.getLogger(__name__)
STOP = set('how to why what where when who the a an is are not for of and with in on ke di yang dan sama soal buat bukan cara kenapa bagaimana alasan pilih apa aja statusnya file dengan tag tempat semua gw jalan mana lagi belum tanggal dikerjain kejadian penting nyebut link'.split())
MONTHS = {'januari':1,'februari':2,'maret':3,'april':4,'mei':5,'juni':6,'juli':7,'agustus':8,'september':9,'oktober':10,'november':11,'desember':12,'january':1,'february':2,'march':3,'may':5,'june':6,'july':7,'august':8,'october':10,'december':12}

def _cfg():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env')
    return {'vault_root':Path(os.getenv('VAULT_ROOT','/home/dxwx/wiki')), 'db_path':os.getenv('LANCEDB_PATH','/home/dxwx/.hermes/vault_vectors'), 'ollama_url':os.getenv('OLLAMA_BASE_URL','http://localhost:11434'), 'embed_model':os.getenv('EMBED_MODEL','bge-m3')}

def tokens(text):
    return set(re.findall(r'[a-z0-9]+',text.lower())) - STOP

def parse_date_range(query, now=None):
    now = now or datetime.now()
    q = query.lower().strip()
    if q in ('kemarin','yesterday'): start = (now-timedelta(days=1)).date(); end=start
    elif q in ('hari ini','today'): start=now.date(); end=start
    elif q in ('minggu lalu','last week'):
        end=now.date()-timedelta(days=now.weekday()+1); start=end-timedelta(days=6)
    elif q in ('bulan lalu','last month'):
        end=now.date().replace(day=1)-timedelta(days=1); start=end.replace(day=1)
    else:
        iso = re.search(r'\b(\d{4}-\d{2}-\d{2})\b',q)
        if iso:
            start=datetime.strptime(iso[1],'%Y-%m-%d').date(); end=start
        else:
            m=re.search(r'\b(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s+('+'|'.join(MONTHS)+r')(?:\s+(\d{4}))?\b',q)
            if not m: return None
            year=int(m[4] or now.year); month=MONTHS[m[3]]
            start=datetime(year,month,int(m[1])).date(); end=datetime(year,month,int(m[2] or m[1])).date()
        if end<start: raise ValueError('Date range end precedes start')
    return datetime.combine(start,datetime.min.time()),datetime.combine(end,datetime.max.time())

def documents():
    root=_cfg()['vault_root'].resolve()
    for p in sorted(root.rglob('*.md')):
        if any(x.startswith('.') for x in p.relative_to(root).parts): continue
        try:
            text=p.read_text(encoding='utf-8')
            fm={}
            if text.startswith('---'):
                parts=text.split('---',2)
                if len(parts)==3: fm=yaml.safe_load(parts[1]) or {}
            if not isinstance(fm,dict): fm={}
            tags=fm.get('tags',[])
            if isinstance(tags,str): tags=tags.split(',')
            if not isinstance(tags,list): tags=[]
            tags={str(t).lower().strip() for t in tags}
            date=str(fm.get('date',''))[:10]
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):
                m=re.match(r'\d{4}-\d{2}-\d{2}',p.name); date=m[0] if m else ''
            status=str(fm.get('status','')).lower()
            if not status:
                status=next((s[7:] for s in sorted(tags) if s.startswith('status/')),'')
            yield {'source':str(p),'text':text,'tags':tags,'date':date,'status':status,'type':str(fm.get('type','')).lower()}
        except (OSError,UnicodeError,yaml.YAMLError) as exc:
            log.warning('Skipping malformed note %s: %s',p,exc)

def result(doc,strategy,score=1.):
    return {'source':doc['source'],'text':doc['text'][:800],'score':score,'chunk_id':doc.get('chunk_id',''),'strategies':[strategy]}

def search_by_tag(tags,limit=50):
    if isinstance(tags,str): tags=tags.split(',')
    wanted={str(t).strip().lower() for t in tags if str(t).strip()}
    if not wanted: return []
    docs=[d for d in documents() if wanted <= d['tags']]
    docs.sort(key=lambda d:(d['date'],d['source']),reverse=True)
    return [result(d,'tag') for d in docs[:limit]]

def search_by_date(date_str,limit=50):
    span=parse_date_range(date_str)
    if not span: raise ValueError('Unrecognized date: '+date_str)
    lo,hi=(d.date().isoformat() for d in span)
    docs=[d for d in documents() if lo<=d['date']<=hi]
    docs.sort(key=lambda d:('/daily-note/' not in d['source'],d['date'],d['source']))
    return [result(d,'date') for d in docs[:limit]]

def search_by_status(status,limit=50,kind=None):
    """Filter explicit status metadata; unknown does not mean unresolved."""
    wanted={'active','open','unresolved','blocked','pending','waiting'} if status=='unresolved' else {status}
    docs=[]
    for d in documents():
        if d['status'] not in wanted: continue
        if kind=='error' and not (d['type'] in ('error','error-log') or '/error-log/' in d['source']): continue
        if kind=='project' and '/05-PROJECT/' not in d['source']: continue
        docs.append(d)
    docs.sort(key=lambda d:(d['date'],d['source']),reverse=True)
    return [result(d,'status') for d in docs[:limit]]

def embed(text):
    import requests
    c=_cfg()
    response=requests.post(c['ollama_url']+'/api/embeddings',json={'model':c['embed_model'],'prompt':text},timeout=30)
    response.raise_for_status()
    vec=response.json()['embedding']
    if not vec: raise RuntimeError('Embedding endpoint returned empty vector')
    return vec

def search_fts(table,query,limit=200,date_range=None):
    return unique_rows(table.search(query,query_type='fts').limit(limit).to_list(),'_score')

def search_vector(table,query,limit=200):
    return unique_rows(table.search(embed(query)).limit(limit).to_list(),'_distance',True)

def informative(row):
    """Reject navigation-only passages before best-passage file deduplication."""
    text=row['text'].strip()
    return not (re.match(r'^#{1,6}\s+(?:related(?: notes| mocs)?|references|see also|links)\b',text,re.I) or (len(text)<180 and text.startswith('#') and len(text.splitlines())<=3))

def unique_rows(rows,key,distance=False):
    out={}
    for row in rows:
        if not informative(row):
            continue
        source=str(Path(row['source']).resolve())
        score= -float(row[key]) if distance else float(row[key])
        if source not in out or score>out[source]['score']:
            out[source]={'score':score,'text':row['text'],'chunk_id':row.get('chunk_id','')}
    return out

def fuse_rankers(rankers,query):
    fused={}
    for strategy,weight,rows in rankers:
        ordered=sorted(rows.items(),key=lambda item:(-item[1]['score'],item[0]))[:60]
        for rank,(source,data) in enumerate(ordered,1):
            if source not in fused: fused[source]={**data,'score':0.,'strategies':[]}
            fused[source]['score']+=weight/(60+rank)
            fused[source]['strategies'].append(strategy)
    # Title boost: helps when filenames contain query-relevant words
    # Many notes have descriptive titles (date-topic-subtopic.md format)
    qt=tokens(query)
    for source,data in fused.items():
        title=re.sub(r'^\d{4}-\d\d-\d\d-','',Path(source).stem)
        data['score']*=1+.5*len(qt & tokens(title))/max(len(qt),1)
    return [dict(source=s,**d) for s,d in sorted(fused.items(),key=lambda item:(-item[1]['score'],item[0]))]

def search_vault(query,top_k=15,mode='broad',strict=False):
    if mode not in ('broad','quick'): raise ValueError('mode must be broad or quick')
    if not query.strip() or top_k<=0: return []
    if parse_date_range(query): return search_by_date(query,top_k)
    tag=re.search(r'\b(?:dengan tag|with tags?|tag:)\s+([\w/, -]+)$',query.lower())
    if tag: return search_by_tag(tag[1],top_k)
    ql=query.lower()
    if re.search(r'\berror\b.*\b(?:belum resolved|unresolved)\b',ql):
        return search_by_status('unresolved',top_k,kind='error')
    if re.search(r'\bprojects?\b.*\b(?:statusnya active|status active|blocked)\b',ql):
        return search_by_status('blocked' if 'blocked' in ql else 'active',top_k,kind='project')
    lesson=bool(re.search(r'\blessons?[- ]learned\b',ql))
    retrieval_query=re.sub(r'\blessons?[- ]learned\b|\bsoal\b',' ',ql).strip() if lesson else query
    import lancedb
    table=lancedb.connect(_cfg()['db_path']).open_table('vault_chunks')
    rankers=[]; degraded=[]
    for name,weight,fn in [('fts',.4,search_fts),('vector',.6,search_vector)]:
        try:
            candidates=fn(table,retrieval_query)
            # Pre-fusion folder filter REMOVED — applied post-fusion instead
            rankers.append((name,weight,candidates))
        except Exception as exc:
            if strict: raise
            log.warning('%s retrieval unavailable: %s',name,exc)
            degraded.append(name)
    if not rankers: raise RuntimeError('Both retrieval channels unavailable')
    ranked=fuse_rankers(rankers,query)
    # Explicit note-type requests constrain results rather than globally boosting folders.
    if re.search(r'\blessons?[- ]learned\b',query.lower()):
        ranked=[r for r in ranked if '/lessons-learned/' in r['source']]
    for r in ranked:
        r['text']=r['text'][:800]; r['score']=round(r['score'],6)
        if degraded: r['degraded']=degraded
    return ranked[:top_k]

if __name__=='__main__':
    import sys,json
    print(json.dumps(search_vault(' '.join(sys.argv[1:]),strict=True),indent=2))
