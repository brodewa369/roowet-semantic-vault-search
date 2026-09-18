#!/usr/bin/env python3
"""hybrid_search.py — Final production search: FTS primary, vector fallback."""

import os
import re
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

LANCEDB_PATH = os.getenv("LANCEDB_PATH", "/home/dxwx/.hermes/vault_vectors")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")

_db = None
_table = None


def _get_table():
    global _db, _table
    if _table is None:
        import lancedb
        _db = lancedb.connect(LANCEDB_PATH)
        _table = _db.open_table("vault_chunks")
    return _table


def _ensure_fts_index():
    t = _get_table()
    try:
        idx_types = [i.index_type for i in t.list_indices()]
        if any("FTS" in str(x) or "INVERTED" in str(x) for x in idx_types):
            return
    except Exception:
        pass
    from lancedb.index import FTS
    t.create_index("text", config=FTS())


def embed_query(text: str) -> list:
    import requests
    r = requests.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": "query: " + text},
        timeout=30,
    )
    if r.status_code == 200:
        return r.json()["embedding"]
    return []


def _parse_date(query: str) -> tuple:
    ql = query.lower()
    now = datetime.now()
    
    if "kemarin" in ql:
        d = now - timedelta(days=1)
        return (d.replace(hour=0, minute=0, second=0), d.replace(hour=23, minute=59, second=59))
    if "hari ini" in ql or "hariini" in ql:
        return (now.replace(hour=0, minute=0, second=0), now.replace(hour=23, minute=59, second=59))
    if "minggu lalu" in ql:
        lw = now - timedelta(days=7)
        return (lw.replace(hour=0, minute=0, second=0), (lw + timedelta(days=6)).replace(hour=23, minute=59, second=59))
    
    patterns = [
        (r'tanggal\s+(\d{1,2})\s*-\s*(\d{1,2})\s+(\w+)', 3),
        (r'tanggal\s+(\d{1,2})\s+(\w+)', 2),
        (r'(\d{1,2})\s*-\s*(\d{1,2})\s+(\w+)', 3),
        (r'(\d{1,2})\s+(\w+)', 2),
    ]
    
    months = {"januari":1,"februari":2,"maret":3,"april":4,"mei":5,"juni":6,"juli":7,"agustus":8,"september":9,"oktober":10,"november":11,"desember":12}
    
    for pattern, ng in patterns:
        m = re.search(pattern, ql)
        if m:
            g = m.groups()
            if ng == 3:
                sd, es, ms = g
                mo = months.get(ms.lower(), 0)
                if mo:
                    return (datetime(now.year, mo, int(sd)), datetime(now.year, mo, int(es), 23, 59, 59))
            elif ng == 2:
                d, ms = g
                mo = months.get(ms.lower(), 0)
                if mo:
                    return (datetime(now.year, mo, int(d)), datetime(now.year, mo, int(d), 23, 59, 59))
    return None


def _en_to_id(query: str) -> str:
    mapping = {
        "how to":"cara","why":"kenapa","what":"apa","where":"dimana","when":"kapan","who":"siapa",
        "structure":"struktur","architecture":"arsitektur","health check":"health check",
        "indexer":"indexer","vault":"vault","telegram":"telegram","cron":"cron",
        "trading":"trading","research":"riset","analysis":"analisis","backup":"backup",
        "migration":"migrasi","error":"error","fix":"fix",
    }
    nq = query.lower()
    for en, idw in mapping.items():
        nq = re.sub(r'\b' + re.escape(en) + r'\b', idw, nq)
    return nq


def search_hybrid(query: str, top_k: int = 8, fetch_k: int = 30, weights=None):
    """FTS-first search. Vector as fallback for zero-FTS queries."""
    date_range = _parse_date(query)
    
    # Build query variants
    queries = [query]
    ql = query.lower()
    en_words = ["how to","why","what","where","when","who","structure","architecture","health check","indexer","vault","telegram","cron","trading","research","analysis","backup","migration"]
    if any(w in ql for w in en_words):
        tq = _en_to_id(query)
        if tq != ql:
            queries.append(tq)
    
    table = _get_table()
    results = {}
    
    for q in queries:
        try:
            _ensure_fts_index()
            rows = table.search(q, query_type="fts").limit(fetch_k).to_list()
            
            for r in rows:
                src = r["source"]
                score = r.get("_relevance", r.get("_score", 0))
                
                # Date filter
                if date_range:
                    idx = r.get("indexed_at", "")
                    if idx:
                        try:
                            if not (date_range[0] <= datetime.fromisoformat(idx) <= date_range[1]):
                                continue
                        except:
                            pass
                
                # Keep best score per source
                if src not in results or score > results[src]["score"]:
                    results[src] = {
                        "score": score,
                        "text": r["text"],
                        "chunk_id": r.get("chunk_id", ""),
                    }
        except:
            pass
    
    # If no FTS results, fallback to vector
    if not results:
        for q in queries:
            vec = embed_query(q)
            if vec:
                try:
                    rows = table.search(vec).limit(top_k).to_list()
                    for r in rows:
                        src = r["source"]
                        dist = r.get("_distance", 999)
                        sim = 1.0 / (1.0 + dist)
                        if src not in results or sim > results[src]["score"]:
                            results[src] = {
                                "score": sim,
                                "text": r["text"],
                                "chunk_id": r.get("chunk_id", ""),
                            }
                except:
                    pass
    
    if not results:
        return []
    
    # Sort by score
    sorted_r = sorted(results.items(), key=lambda x: -x[1]["score"])
    
    return [
        {
            "source": src,
            "text": data["text"][:800],
            "score": round(data["score"], 4),
            "chunk_id": data.get("chunk_id", ""),
        }
        for src, data in sorted_r[:top_k]
    ]


def search_by_tag(tags: list, top_k: int = 10) -> list:
    """Search files by frontmatter tags."""
    from pathlib import Path
    import yaml
    
    VAULT_ROOT = Path("/home/dxwx/wiki")
    EXCLUDE_DIRS = {".obsidian", ".git", "__pycache__", "06-SYSTEM", "07-INDEX"}
    
    tags_lower = [t.lower() for t in tags]
    matches = []
    
    for root, dirs, files in os.walk(VAULT_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        
        for fname in files:
            if not fname.endswith(".md"):
                continue
            
            filepath = os.path.join(root, fname)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if not content.startswith("---"):
                    continue
                
                parts = content.split("---", 2)
                if len(parts) < 3:
                    continue
                
                fm = yaml.safe_load(parts[1]) or []
                fm_tags = [t.lower() for t in fm.get("tags", [])]
                
                # Check if any query tag matches
                matching = set(tags_lower) & set(fm_tags)
                if matching:
                    matches.append({
                        "source": str(Path(filepath).relative_to(VAULT_ROOT)),
                        "tags": fm_tags,
                        "match_count": len(matching),
                    })
            except:
                pass
    
    # Sort by match count
    matches.sort(key=lambda x: -x["match_count"])
    return matches[:top_k]


def search_by_date(date_str: str, top_k: int = 10) -> list:
    """Search files by date (YYYY-MM-DD or relative like 'kemarin', 'minggu lalu')."""
    date_str = date_str.lower().strip()
    now = datetime.now()
    
    if date_str in ["kemarin", "yesterday"]:
        target = now - timedelta(days=1)
    elif date_str in ["hari ini", "today"]:
        target = now
    elif "minggu lalu" in date_str:
        target = now - timedelta(days=7)
    elif "bulan lalu" in date_str:
        target = now - timedelta(days=30)
    else:
        try:
            target = datetime.strptime(date_str, "%Y-%m-%d")
        except:
            return [{"error": f"Cannot parse date: {date_str}"}]
    
    date_formatted = target.strftime("%Y-%m-%d")
    table = _get_table()
    results = []
    
    try:
        _ensure_fts_index()
        rows = table.search(date_formatted, query_type="fts").limit(top_k).to_list()
        for r in rows:
            results.append({
                "source": r["source"],
                "text": r["text"][:800],
                "score": r.get("_score", 0.5),
            })
    except:
        pass
    
    return results


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "wallet 0xa70fc67c cashcat"
    for r in search_hybrid(q, top_k=5):
        print(f"{r['score']:.4f} {r['source'].split('wiki/')[-1]}")
