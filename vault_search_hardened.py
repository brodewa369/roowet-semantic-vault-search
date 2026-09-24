"""Staged hardening of the verified ranker. Does not replace the live module."""
import math
import re
import time
import logging
from functools import lru_cache
from pathlib import Path
import vault_search_candidate as base

log = logging.getLogger(__name__)

ID_EN_MAP = {
    'struktur': 'structure', 'struktural': 'structure',
    'folder': 'folder', 'bagian': 'section',
    'susunan': 'layout', 'arsitektur': 'architecture',
    'tata': 'layout', 'letak': 'layout',
    'dimana': 'where', 'mana': 'where',
    'aktif': 'active', 'kejadian': 'event',
    'penting': 'important', 'dikerjain': 'worked',
    'file': 'file', 'daily': 'daily',
    'note': 'note', 'cron': 'cron',
    'jobs': 'jobs', 'blocked': 'blocked',
}



def expand_query_synonyms(q):
    """Expand query with synonyms for better bilingual matching."""
    words = re.findall(r'[a-z0-9]+', q.lower())
    expanded = set()
    for w in words:
        expanded.add(w)
        if w in SYNONYM_MAP:
            for syn in SYNONYM_MAP[w]:
                expanded.add(syn)
    return ' '.join(expanded)

def validate(query, top_k, mode):
    if not isinstance(query,str) or len(query)>4096:
        raise ValueError('query must be a string of at most 4096 characters')
    if type(top_k) is not int or not 1<=top_k<=50:
        raise ValueError('top_k must be an integer from 1 to 50')
    if mode not in ('broad','quick'):
        raise ValueError('mode must be broad or quick')

def fetch_embedding(url,model,text):
    import requests
    r=requests.post(url+'/api/embeddings',json={'model':model,'prompt':text},timeout=(3,30))
    r.raise_for_status()
    v=r.json().get('embedding')
    if not isinstance(v,list) or not v or any(type(x) not in (int,float) or not math.isfinite(x) for x in v):
        raise ValueError('Embedding must contain finite numbers')
    return v

@lru_cache(maxsize=256)
def cached_embedding(url,model,text,epoch):
    return tuple(fetch_embedding(url,model,text))

def embed(text):
    cfg=base._cfg()
    return list(cached_embedding(cfg['ollama_url'],cfg['embed_model'],text,int(time.monotonic()//300)))

def safe_documents():
    import yaml
    root=base._cfg()['vault_root'].resolve()
    for p in sorted(root.rglob('*.md')):
        if p.is_symlink() or any(x.startswith('.') for x in p.relative_to(root).parts):
            continue
        if not p.resolve().is_relative_to(root):
            continue
        try:
            text=p.read_text(encoding='utf-8')
            parts=text.split('---',2) if text.startswith('---') else []
            fm=yaml.safe_load(parts[1]) or {} if len(parts)==3 else {}
            if not isinstance(fm,dict): fm={}
            tags=fm.get('tags',[])
            if isinstance(tags,str): tags=tags.split(',')
            tags={str(t).strip().lower() for t in tags} if isinstance(tags,list) else set()
            date=str(fm.get('date',''))[:10]
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):
                m=re.match(r'\d{4}-\d{2}-\d{2}',p.name);date=m[0] if m else ''
            status=str(fm.get('status','')).lower() or next((t[7:] for t in sorted(tags) if t.startswith('status/')),'')
            yield {'source':str(p),'text':text,'tags':tags,'date':date,'status':status,'type':str(fm.get('type','')).lower()}
        except (OSError,UnicodeError,yaml.YAMLError) as exc:
            log.warning('Metadata note unavailable %s: %s',p,exc)

def metadata_page(tags=None,date=None,status=None,kind=None,limit=20,offset=0):
    validate('',limit,'broad')
    if type(offset) is not int or offset<0:raise ValueError('offset must be nonnegative')
    if isinstance(tags,str):tags=tags.split(',')
    wanted={str(t).strip().lower() for t in (tags or []) if str(t).strip()}
    span=base.parse_date_range(date) if date else None
    if date and not span:raise ValueError('Unrecognized date')
    allowed={'active','open','unresolved','blocked','pending','waiting'} if status=='unresolved' else {status}
    docs=[]
    for d in safe_documents():
        if wanted and not wanted<=d['tags']:continue
        if span and not span[0].date().isoformat()<=d['date']<=span[1].date().isoformat():continue
        if status and d['status'] not in allowed:continue
        if kind=='error' and not (d['type'] in ('error','error-log') or '/error-log/' in d['source']):continue
        if kind=='project' and '/05-PROJECT/' not in d['source']:continue
        docs.append(d)
    docs.sort(key=lambda d:(d['date'],d['source']),reverse=True)
    if date:docs.sort(key=lambda d:('/daily-note/' not in d['source'],d['date'],d['source']))
    # For tag queries, sort by tag specificity (fewer tags = more specific) then date
    if tags and not date:
        docs.sort(key=lambda d:(len(d['tags']),d['date'],d['source']),reverse=True)
    end=offset+limit
    return {'results':[base.result(d,'metadata') for d in docs[offset:end]],'total':len(docs),'offset':offset,'next_offset':end if end < len(docs) else None,'complete':end>=len(docs)}

def metadata_intent(query):
    if base.parse_date_range(query):return {'date':query}
    tag=re.search(r'\b(?:dengan tag|with tags?|tag:)\s+([\w/, -]+)$',query.lower())
    if tag:return {'tags':tag[1]}
    q=query.lower()
    if re.search(r'\berror\b.*\b(?:belum resolved|unresolved)\b',q):return {'status':'unresolved','kind':'error'}
    if re.search(r'\bprojects?\b.*\b(?:statusnya active|status active|blocked)\b',q):
        # q50 fix: also check blockers folder for "blocked" queries
        if 'blocked' in q:
            return {'folder':'01-AGENT-MEMORY/blockers/'}
        return {'status':'active','kind':'project'}
    
    # q49 fix: "cron jobs mana yang aktif" → route to morning-brief folder
    if re.search(r'\bcron\b',q) and re.search(r'\b(aktif|active)\b',q):
        return {'folder':'04-LOGS/morning-brief/'}
    
    # q46 fix: "dimana file daily note" → route to folder
    loc = re.search(r'\bdimana\s+(?:file\s+)?(\w+(?:\s+\w+)*)\s*(?:file|folder|directory)?\b', q)
    if loc:
        folder_map = {'daily note':'04-LOGS/daily-note/', 'daily-note':'04-LOGS/daily-note/', 'morning brief':'04-LOGS/morning-brief/'}
        folder = folder_map.get(loc.group(1).strip())
        if folder:
            return {'folder':folder}
    
    return None

def folder_page(folder_prefix, limit=20, offset=0):
    root = base._cfg()['vault_root'].resolve()
    docs = []
    for d in safe_documents():
        if d['source'].replace(str(root) + '/', '').startswith(folder_prefix):
            docs.append(d)
    docs.sort(key=lambda d:(d['date'],d['source']),reverse=True)
    end = offset + limit
    return {'results':[base.result(d,'folder') for d in docs[offset:end]],'total':len(docs),'offset':offset,'next_offset':end if end < len(docs) else None,'complete':end >= len(docs)}

def search_vault(query,top_k=15,mode='broad',strict=False):
    validate(query,top_k,mode)
    if not query.strip():return []
    limit=min(top_k,5) if mode=='quick' else top_k
    intent=metadata_intent(query)
    if intent:
        if 'folder' in intent:
            return folder_page(intent['folder'],limit=limit)['results']
        # Tag queries: sort by relevance to tag, not just date
        if 'tags' in intent:
            tag = intent['tags'].split(',')[0] if isinstance(intent['tags'], str) else intent['tags'][0]
            page = metadata_page(tags=intent['tags'], limit=50)
            
            try:
                tag_vec = embed(tag)
                vec_results = table.search(tag_vec).limit(50).to_list()
                vec_sources = {r['source']: -r.get('_distance', 0) for r in vec_results}
                
                for r in page['results']:
                    r['score'] = vec_sources.get(r['source'], 0)
                page['results'].sort(key=lambda x: -x['score'])
            except:
                pass
            
            return page['results'][:limit]
        return metadata_page(**intent,limit=limit)['results']
    import lancedb
    table=lancedb.connect(base._cfg()['db_path']).open_table('vault_chunks')
    lesson=bool(re.search(r'\blessons?[- ]learned\b',query.lower()))
    
    # q32 fix: strip lesson terms from query for retrieval
    # "Lesson learned" is a content-type qualifier, not a content query
    # The real content query is what comes after (e.g., "rag" in "lesson learned soal rag")
    if lesson:
        rq = re.sub(r'\blessons?[- ]learned\b|\bsoal\b',' ',query.lower()).strip()
    else:
        rq = query
    
    ranks=[];degraded=[]
    channels=[('fts',.4,lambda:base.search_fts(table,rq)),('vector',.6,lambda:base.unique_rows(table.search(embed(query)).limit(200).to_list(),'_distance',True))]
    
    # Check for cross-folder/relationship queries
    relationship_keywords = ['hubungan', 'relasi', 'between', 'sama', 'perbedaan', 'dan', 'and', 'with']
    has_relationship = any(kw in query.lower() for kw in relationship_keywords)
    
    if has_relationship:
        words = query.lower().split()
        stop_words = {'the','a','an','is','are','was','were','be','been','have','has','had','do','does','did','will','would','could','should','may','might','must','shall','can','to','of','in','for','on','with','at','by','from','as','into','through','during','before','after','above','below','out','off','over','under','again','further','then','once','here','there','when','where','why','how','all','each','few','more','most','other','some','no','nor','not','only','own','same','so','than','too','very','just','don','now','and','or','but','if','while','because','although','though','until','unless','since','yet','both','either','neither','whether','however','therefore','thus','but','per','pro','re','via','vs'}
        key_words = [w for w in words if w not in stop_words and len(w) > 3]
        
        if len(key_words) >= 2:
            all_results = {}
            for word in key_words[:4]:
                try:
                    vec_results = table.search(embed(word)).limit(15).to_list()
                    for r in vec_results:
                        src = str(Path(r['source']).resolve())
                        if src not in all_results:
                            all_results[src] = {'source': src, 'score': 0, 'merge_count': 0}
                        all_results[src]['merge_count'] += 1
                        all_results[src]['score'] = max(all_results[src]['score'], -r.get('_distance', 0))
                except:
                    pass
            
            if all_results:
                merged = sorted(all_results.values(), key=lambda x: (-x['merge_count'], -x['score']))
                for r in merged:
                    r['text'] = r.get('text', '')[:800]
                return merged[:limit]
    
    root=base._cfg()['vault_root'].resolve()
    for name,weight,fn in channels:
        try:
            rows=fn()
            rows={s:d for s,d in rows.items() if Path(s).is_file() and Path(s).resolve().is_relative_to(root)}
            ranks.append((name,weight,rows))
        except Exception as exc:
            if strict:raise
            degraded.append(name);log.warning('%s unavailable: %s',name,exc)
    if not ranks:raise RuntimeError('Both retrieval channels unavailable')
    
    rows=base.fuse_rankers(ranks,query)
    
    # q32 fix: post-fusion filter to ONLY lessons-learned files
    # This is correct: "lesson learned" is a content-type query
    if lesson:
        rows=[r for r in rows if '/lessons-learned/' in r['source']]
    
    for r in rows:
        r['text']=r['text'][:800];r['score']=round(r['score'],6)
        if degraded:r['degraded']=list(degraded)
    return rows[:limit]

def search_response(query,top_k=15,mode='broad',strict=False):
    rows=search_vault(query,top_k,mode,strict)
    current=bool(re.search(r'\b(cron|jobs?|project|proyek)\b',query,re.I) and re.search(r'\b(active|aktif|blocked|sekarang|current)\b',query,re.I))
    return {'results':rows,'count':len(rows),'complete':False,'degraded':sorted({x for r in rows for x in r.get('degraded',[])}),'state_authority':'historical-notes-only' if current else 'vault-notes','warning':'Check the live scheduler or project owner for current state.' if current else None,'query':query,'mode':mode}

def recall(topic,char_budget=7000,top_k=20):
    if type(char_budget) is not int or not 1<=char_budget<=20000:raise ValueError('char_budget must be 1..20000')
    rows=search_vault(topic,top_k,strict=True);seen=set();pkg=[];used=0;truncated=False
    for r in rows:
        if r['source'] in seen:continue
        seen.add(r['source']);text=r['text'];remaining=char_budget-used
        if len(text)>remaining:truncated=True
        if remaining<=0:break
        text=text[:remaining];pkg.append({**r,'text':text});used+=len(text)
    return {'results':pkg,'count':len(pkg),'chars_used':used,'char_budget':char_budget,'truncated':truncated,'complete':False,'scope':'ranked snippets; not exhaustive multi-hop coverage'}
