"""Bounded multi-document context with deterministic, snapshot-checked pages.
No retrieval-score changes. Filesystem enumeration is still O(vault size).
"""
import hashlib
import json
import re
from pathlib import Path


def body(text):
    text=re.sub(r'\A---\s*\n.*?\n---\s*(?:\n|$)', '', text, count=1, flags=re.S)
    out=[]; skipping=None; fence=None
    for line in text.splitlines():
        stripped=line.lstrip()
        marker=re.match(r'^(`{3,}|~{3,})',stripped)
        if marker:
            if fence is None:fence=marker[1][0]
            elif marker[1][0]==fence:fence=None
        heading=None if fence else re.match(r'^(#{1,6})\s+(.+)',stripped)
        if heading:
            level=len(heading[1])
            if skipping is not None and level<=skipping:skipping=None
            if re.fullmatch(r'(?:related(?: notes| mocs)?|references|see also|links)\s*',heading[2],re.I):skipping=level
        if skipping is None:out.append(line)
    return '\n'.join(out).strip()


def passage(text,topic,backend,hint=''):
    """Prefer the indexed winning passage if present, otherwise lexical windows."""
    if not text:return '',0
    cleaned=' '.join(text.split()); wanted=' '.join(hint.split())
    if len(wanted)>=40:
        # Only use the hint when it can be grounded in the current body.
        pos=cleaned.casefold().find(wanted.casefold())
        if pos>=0:return cleaned[pos:pos+1500],pos
    qt=backend.base.tokens(topic)
    starts={0}
    for match in re.finditer(r'\n\s*\n|\n(?=#{1,6}\s)',text):starts.add(match.end())
    starts.update(range(0,len(text),200))
    start=max(sorted(starts),key=lambda i:(len(qt & backend.base.tokens(text[i:i+250])),-i))
    return text[start:start+1500],start


def recall(params,backend):
    topic=params.get('topic','');top_k=params.get('top_k',20);budget=params.get('char_budget',7000)
    offset=params.get('offset',0);provided=params.get('snapshot')
    backend.validate(topic,top_k,'broad')
    if not topic.strip():raise ValueError('topic is required')
    if type(budget) is not int or not 1<=budget<=20000:raise ValueError('char_budget must be 1..20000')
    if type(offset) is not int or offset<0:raise ValueError('offset must be a nonnegative integer')
    if offset and not isinstance(provided,str):raise ValueError('continuation requires snapshot from the first page')
    root=backend.base._cfg()['vault_root'].resolve()
    seeds=backend.search_vault(topic,top_k,strict=True)
    docs={d['source']:d for d in backend.safe_documents()}
    queue={};links={};unresolved=set();clusters={}
    for row in seeds:
        queue.setdefault(row['source'],('seed',row))
        parent=Path(row['source']).parent
        try:parts=parent.relative_to(root).parts
        except ValueError:continue
        # A project-specific directory is a meaningful cluster. Generic error,
        # research and daily-note directories are not topical clusters.
        if len(parts)>=3 and parts[0]=='05-PROJECT' and parts[1] in ('active','archive'):
            clusters.setdefault(parent,[]).append(row['source'])
    clusters={p:s for p,s in clusters.items() if len(s)>=2}
    by_stem={}
    for path in docs:by_stem.setdefault(Path(path).stem,[]).append(path)
    for row in seeds:
        source=row['source']
        for target in re.findall(r'\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]',docs.get(source,{}).get('text','')):
            target=target.strip();p=Path(target if target.endswith('.md') else target+'.md')
            if p.is_absolute() or '..' in p.parts:unresolved.add(target);continue
            matches=sorted({str((root/p).resolve()),str((Path(source).parent/p).resolve())} & docs.keys())
            if not matches and len(p.parts)==1:matches=by_stem.get(p.stem,[])
            if len(matches)!=1:unresolved.add(target);continue
            path=matches[0];links.setdefault(path,[]).append(source)
            queue.setdefault(path,('neighbor',{}))
    # Explicit links precede directory adjacency; both remain visibly heuristic.
    for parent in sorted(clusters):
        for path in sorted(docs):
            if Path(path).parent==parent:queue.setdefault(path,('sibling',{}))
    manifest=hashlib.sha256()
    manifest.update(json.dumps([topic,top_k,list(queue)],ensure_ascii=False).encode())
    for path in queue:
        manifest.update(path.encode());manifest.update(docs.get(path,{}).get('text','<unavailable>').encode())
    snapshot=manifest.hexdigest()
    if provided is not None and provided!=snapshot:raise ValueError('recall snapshot changed; restart at offset 0')
    candidates=[];excluded={};bodies={}
    for path,(kind,row) in queue.items():
        if path not in docs:excluded[path]='unavailable';continue
        text=body(docs[path]['text'])
        if not text or not re.sub(r'(?m)^#[^\n]*$|\[\[[^\]]+\]\]|<!--[^\n]*-->','',text).strip():
            excluded[path]='navigation-only';continue
        evidence,start=passage(text,topic,backend,row.get('text',''))
        bodies[path]=(evidence,len(text),start)
        candidates.append({'source':path,'score':row.get('score',0.),'chunk_id':row.get('chunk_id',''),
                           'strategies':['progressive-recall-v2'],'expansion':kind,'is_seed':kind=='seed',
                           'is_neighbor':kind!='seed','linked_from':sorted(set(links.get(path,[]))),
                           'cluster_from':clusters.get(Path(path).parent,[]) if kind=='sibling' else []})
    if offset>len(candidates):raise ValueError('offset exceeds candidate count')
    result=[];used=0;end=offset
    for candidate in candidates[offset:]:
        if used>=budget or len(result)>=40:break
        evidence,_,start=bodies[candidate['source']]
        text=evidence[:min(250,budget-used)]
        result.append({**candidate,'text':text,'chars':len(text),'body_offset':start})
        used+=len(text);end+=1
    for row in result:
        evidence,_,_=bodies[row['source']]
        extra=evidence[row['chars']:row['chars']+budget-used]
        row['text']+=extra;row['chars']+=len(extra);used+=len(extra)
    partial=[r['source'] for r in result if r['body_offset']>0 or r['chars']<bodies[r['source']][1]]
    omitted=[r['source'] for r in candidates[end:]]+list(excluded)
    return {'topic':topic,'results':result,'count':len(result),'files_included':len(result),
            'seed_sources':[r['source'] for r in seeds],'chars_used':used,'char_budget':budget,
            'budget_scope':'evidence text only; metadata and source paths are additional',
            'neighbors_included':sum(r['is_neighbor'] for r in result),
            'expansion_counts':{k:sum(r['expansion']==k for r in result) for k in ('seed','neighbor','sibling')},
            'cluster_dirs':[str(p.relative_to(root)) for p in sorted(clusters)],
            'total_candidates':len(candidates),'offset':offset,'next_offset':end if end<len(candidates) else None,
            'snapshot':snapshot,'candidate_page_complete':end==len(candidates),
            'complete':False,'truncated':bool(omitted or partial),'omitted_sources':omitted,
            'excluded_sources':excluded,'partial_sources':partial,'unresolved_links':sorted(unresolved),
            'scope':'ranked seeds, exact one-hop links and project-directory siblings; not exhaustive topic discovery',
            'follow_up':'Follow next_offset with the same topic, top_k and snapshot; read partial sources before making claims requiring full evidence.'}
