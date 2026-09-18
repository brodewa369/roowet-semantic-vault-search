"""Experimental bounded passage reranker; no golden labels or production wiring.
Input: baseline file ranks plus raw channel chunks from that same retrieval.
No remote calls. Scores are lexical, NOT a cross-encoder or semantic model.
"""
import math
import re
from collections import Counter, defaultdict

STOP = set('how to why what where when who the a an is are not for of and with in on ke di yang dan sama soal buat bukan cara kenapa bagaimana alasan pilih apa aja statusnya file dengan tag tempat semua gw jalan mana lagi belum tanggal dikerjain kejadian penting nyebut link'.split())
IDENT = re.compile(r'(?<![\w.-])(?:[\w-]+\.(?:dll|py|js|json|yaml|toml|md)|0x[a-fA-F0-9]{8,})(?![\w.-])', re.I)

def tokens(text):
    return set(re.findall(r'[a-z0-9]+', text.lower())) - STOP

def identifiers(text):
    return tuple(dict.fromkeys(m.group().lower() for m in IDENT.finditer(text)))

def contains(text, value):
    if value.startswith('0x'):
        # Addresses are quoted at different lengths; a hex continuation of the
        # same address counts, while a longer identifier must never match a
        # shorter query identifier.
        return re.search(r'(?<![\w.-])'+re.escape(value)+r'[0-9a-fA-F]*(?![\w.-])', text, re.I) is not None
    return re.search(r'(?<![\w.-])'+re.escape(value)+r'(?![\w.-])', text, re.I) is not None

def evidence_window(text, query, limit=800):
    if len(text)<=limit:
        return text
    anchors=list(identifiers(query)) or sorted(tokens(query),key=lambda x:(-len(x),x))
    pos=next((m.start() for term in anchors if (m:=re.search(re.escape(term),text,re.I))),0)
    start=max(0,min(pos-160,len(text)-limit))
    return text[start:start+limit]

def rerank(query, baseline, chunks, mode='combined', pool_size=30):
    if mode not in ('identifier','passage','combined'):
        raise ValueError('unknown reranking mode')
    if not 1<=pool_size<=100:
        raise ValueError('pool_size must be 1..100')
    pool=[dict(row) for row in baseline[:pool_size]]
    if not pool:return []
    sources={r['source'] for r in pool}
    bysource=defaultdict(dict)
    for chunk in chunks:
        if chunk['source'] in sources:
            bysource[chunk['source']].setdefault(chunk['text'],chunk)
    # Document frequency, not chunk frequency: duplicates cannot amplify evidence.
    df=Counter()
    for source in sources:
        terms=set()
        for text in bysource[source]:terms.update(tokens(text))
        df.update(terms)
    qt=tokens(query)
    weights={t:math.log(1+(len(pool)+1)/(df[t]+1)) for t in qt}
    denom=sum(weights.values()) or 1
    ids=identifiers(query)
    for row in pool:
        candidates=list(bysource[row['source']].values()) or [row]
        def passage_key(chunk):
            text=chunk['text']
            exact=sum(contains(text,x) for x in ids)
            cov=sum(weights[t] for t in qt & tokens(text))/denom
            return exact,cov,-len(text),text
        best=max(candidates,key=passage_key)
        exact,cov,_,_=passage_key(best)
        # Single identifiers: file-level presence suffices because retrieved
        # chunks may split one document. Multiple identifiers: all must coexist
        # in one passage; file-level unions cannot fabricate connected evidence.
        union=all(any(contains(text,x) for text in bysource[row['source']]) for x in ids)
        row['identifier_match']=bool(ids) and (exact==len(ids) if len(ids)>1 else union)
        row['passage_coverage']=cov
        row['text']=evidence_window(best['text'],query)
        row['chunk_id']=best.get('chunk_id','')
        row['rerank_score']=row['score']*(1+.12*cov) if mode!='identifier' else row['score']
        row['rerank_mode']=mode
    indexed=list(enumerate(pool))
    indexed.sort(key=lambda p:(-int(p[1]['identifier_match'] and mode!='passage'),-p[1]['rerank_score'],p[0]))
    return [r for _,r in indexed]+[dict(r) for r in baseline[pool_size:]]
