"""
semantic_search_mcp.py — MCP Server for Obsidian Vault Semantic Search (v2 — hybrid)

Tools:
- search_vault(query, top_k) → hybrid search (vector + FTS via RRF, token-coverage gated)
- recall(topic, char_budget) → multi-query context package: hybrid search on the
  topic + query variants, 1-hop [[wikilink]] neighbors, deduped and trimmed to budget
- read_vault_sections(filepath, sections) → read only specific '##' sections of a file
- read_vault_file(filepath) → full file content
- get_chunk(source) → all chunks for one source file
- vault_stats() → index statistics
- reindex_file(filepath) → reindex one file
- index_stats() → hash-store stats + chunk count + staleness
- vault_doctor() → health check: stale files, orphans, dup chunks, index age

v2 changes (2026-09-13):
- search_vault now uses hybrid_search.search_hybrid (BM25+vector RRF, token gate, per-file cap)
- snippet length 300 → 800 chars (configurable via SNIPPET_CHARS)
- NEW recall(): single-call context package with char budget
- NEW read_vault_sections(): token-efficient section reads
- NEW vault_doctor(): index health report
- query log: ~/.hermes/vault_vectors/query_log.jsonl (append, rotated at 5MB)
"""

import os
import sys
import json
import re
import logging
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

import requests  # Always needed

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("semantic_mcp")

# ── Config (env-var driven) ─────────────────────────────────────────────────

VAULT_ROOT = os.getenv("VAULT_ROOT", "./vault")
LANCEDB_PATH = os.getenv("LANCEDB_PATH", "./data/lancedb")
_db_dir = os.path.dirname(LANCEDB_PATH) if os.path.dirname(LANCEDB_PATH) else "."
HASH_STORE_PATH = os.getenv("HASH_STORE_PATH", os.path.join(_db_dir, "vault_indexer_hashes.json"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
SNIPPET_CHARS = int(os.getenv("SNIPPET_CHARS", "800"))
RECALL_CHAR_BUDGET = int(os.getenv("RECALL_CHAR_BUDGET", "7000"))
QUERY_LOG_PATH = os.getenv("QUERY_LOG_PATH", os.path.join(_db_dir, "query_log.jsonl"))
QUERY_LOG_MAX_BYTES = int(os.getenv("QUERY_LOG_MAX_BYTES", str(5 * 1024 * 1024)))

# hybrid_search lives next to this script
sys.path.insert(0, str(Path(__file__).parent))

# ── MCP Protocol (stdio) ────────────────────────────────────────────────────

def read_request():
    line = sys.stdin.readline()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None

def write_response(response):
    print(json.dumps(response), flush=True)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _log_query(tool: str, query: str, results: list):
    """Append to query log (hygiene signal for Phase 4 vault doctor)."""
    try:
        p = Path(QUERY_LOG_PATH)
        if p.exists() and p.stat().st_size > QUERY_LOG_MAX_BYTES:
            rotated = p.with_suffix(".jsonl.1")
            if rotated.exists():
                rotated.unlink()
            p.rename(rotated)
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "tool": tool,
            "query": query[:200],
            "files": [r["source"].replace(VAULT_ROOT, "").lstrip("/") for r in results[:8]],
        }
        with open(p, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # logging must never break search

def _resolve_vault_path(file_path: str) -> str:
    p = Path(file_path)
    if not p.is_absolute():
        file_path = str(Path(VAULT_ROOT) / file_path)
    return file_path

def _frontmatter_meta(content: str) -> dict:
    """Parse YAML-ish frontmatter without pyyaml dependency (best-effort)."""
    meta = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip().strip("[]\"' ")
    return meta

WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")

def _wikilinks(content: str) -> list:
    return [m.group(1).strip() for m in WIKILINK_RE.finditer(content)]

def _find_by_title(title: str):
    """Locate a vault file by note title (wikilink resolution)."""
    t = title.lower()
    cands = []
    vault = Path(VAULT_ROOT)
    for f in vault.rglob("*.md"):
        rel = str(f.relative_to(vault))
        low = rel.lower()
        if low.endswith(title.lower() + ".md") or title.lower() in low.replace(" ", "-"):
            cands.append(str(f))
        if len(cands) >= 4:
            break
    return cands


def _find_folder_index(topic: str) -> str | None:
    """Find folder index.md matching the topic. Returns path or None."""
    topic_lower = topic.lower().replace("-", " ").replace("_", " ")
    words = set(topic_lower.split())
    
    for root, dirs, files in os.walk(VAULT_ROOT):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "06-SYSTEM"]
        if "index.md" not in files:
            continue
        
        folder_name = os.path.basename(root).lower()
        folder_words = set(folder_name.replace("-", " ").replace("_", " ").split())
        
        # Exact match
        if topic_lower == folder_name.replace("-", " ").replace("_", " "):
            return os.path.join(root, "index.md")
        
        # All topic words appear in folder name
        if words.issubset(folder_words):
            return os.path.join(root, "index.md")
        
        # Folder name contains topic as substring
        clean = folder_name.replace("-", "").replace("_", "")
        if topic_lower.replace(" ", "") in clean:
            return os.path.join(root, "index.md")
    
    return None


def _recall_from_folder(index_path: str, budget: int) -> list:
    """Read folder index.md and return top files as recall package."""
    try:
        content = Path(index_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    
    pkg = []
    used = 0
    
    # Add index content first
    index_text = content[:1500]
    pkg.append({
        "source": index_path,
        "text": index_text,
        "score": 1.0,
        "is_index": True,
    })
    used += len(index_text)
    
    # Parse related files from index
    lines = content.splitlines()
    for line in lines:
        if used > budget:
            break
        # Look for wikilinks in format [[filename]]
        match = re.search(r'\[\[([^\]|#]+)', line)
        if match:
            title = match.group(1).strip()
            # Resolve to file
            for cand in _find_by_title(title):
                try:
                    file_content = Path(cand).read_text(encoding="utf-8", errors="replace")
                    snip = file_content[:800]
                    pkg.append({
                        "source": cand,
                        "text": snip,
                        "score": 0.5,
                    })
                    used += len(snip)
                    if used > budget:
                        break
                except Exception:
                    pass
    
    return pkg

# ── Tools ────────────────────────────────────────────────────────────────────

def get_db():
    import lancedb
    db = lancedb.connect(LANCEDB_PATH)
    return db.open_table("vault_chunks")

def tool_search_vault(params: dict) -> dict:
    """Multi-strategy vault search (v4): FTS + vector + tags, returns ALL relevant files across folders."""
    query = params.get("query", "")
    if not query:
        return {"error": "query is required"}
    
    top_k = min(max(params.get("top_k", 15), 1), 50)
    mode = params.get("mode", "broad")
    
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import vault_search_hardened as hardened
        results = hardened.search_response(query, top_k=top_k, mode=mode, strict=True)
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}

    _log_query("search_vault", query, results.get("results", []))

    return {
        "results": [
            {
                "source": r["source"],
                "text": r["text"][:SNIPPET_CHARS],
                "score": r.get("score", 0),
                "chunk_id": r.get("chunk_id", ""),
                "strategies": r.get("strategies", []),
                "degraded": r.get("degraded", []),
            }
            for r in results.get("results", [])
        ],
        "count": results.get("count", len(results.get("results", []))),
        "complete": results.get("complete", False),
        "degraded": results.get("degraded", []),
        "state_authority": results.get("state_authority", "vault-notes"),
        "warning": results.get("warning"),
        "query": query,
        "mode": mode,
    }


def tool_search_by_tag(params: dict) -> dict:
    """Search files by frontmatter tags.
    
    Example: {"tags": ["crypto", "active"], "top_k": 10}
    """
    tags = params.get("tags", [])
    if not tags:
        return {"error": "tags array required"}
    
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    
    top_k = min(max(params.get("top_k", 10), 1), 50)
    
    try:
        import hybrid_search
        matches = hybrid_search.search_by_tag(tags, top_k=top_k)
    except Exception as e:
        return {"error": str(e)}
    
    return {
        "count": len(matches),
        "tags": tags,
        "results": matches,
    }


def tool_search_by_date(params: dict) -> dict:
    """Search files by date (YYYY-MM-DD or relative: 'kemarin', 'hari ini', 'minggu lalu', 'bulan lalu').
    
    Example: {"date": "2026-09-16", "top_k": 10}
    Example: {"date": "kemarin", "top_k": 10}
    """
    date_str = params.get("date", params.get("query", ""))
    if not date_str:
        return {"error": "date string required"}
    
    top_k = min(max(params.get("top_k", 10), 1), 50)
    
    try:
        import hybrid_search
        results = hybrid_search.search_by_date(date_str, top_k=top_k)
    except Exception as e:
        return {"error": str(e)}
    
    return {
        "count": len(results),
        "date": date_str,
        "results": results,
    }

def tool_recall(params: dict) -> dict:
    """Context package: search topic + variants, add 1-hop wikilink neighbors, trim to char budget.
    
    If topic matches a folder name, returns folder index.md + top files.
    """
    topic = params.get("topic", params.get("query", ""))
    budget = min(max(int(params.get("char_budget", RECALL_CHAR_BUDGET)), 1000), 20000)
    if not topic:
        return {"error": "topic is required"}

    import hybrid_search
    
    # P0.2: Check if topic matches a folder name — return folder index
    folder_index = _find_folder_index(topic)
    if folder_index:
        pkg = _recall_from_folder(folder_index, budget)
        _log_query("recall-folder", topic, pkg)
        return {"topic": topic, "count": len(pkg), "char_budget": budget, "chars_used": sum(len(p.get("text", "")) for p in pkg), "neighbors_included": 0, "from_folder": True, "package": pkg}

    # Query expansion: original + Indonesian/English variants + synonym injection
    queries = [topic]
    low = topic.lower()
    # Indonesian "how-to" expansion
    if "cara" not in low and "how" not in low:
        queries.append(f"cara {topic}")
    # English form
    if "how to" not in low:
        queries.append(f"how to {topic}")
    # Synonym injection (common vault vocabulary)
    synonym_map = {
        "setup": "setup config configuration",
        "config": "setup config configuration",
        "error": "error bug issue fix",
        "fix": "error bug issue fix",
        "install": "installation setup",
        "deploy": "deployment release",
        "backup": "backup restore",
        "migration": "migration move transfer",
        "wallet": "wallet address token",
        "token": "token coin memecoin",
        "bot": "bot automation script",
        "trading": "trading trade strategy",
        "mining": "mining stake yield",
        "research": "research analysis report",
        "analysis": "analysis report research",
        "security": "security audit vulnerability",
        "audit": "audit review test",
        "backup": "backup restore",
        "docker": "docker container",
        "linux": "linux server ubuntu",
        "database": "database sql postgres",
        "api": "api endpoint",
        "ui": "ui frontend interface",
    }
    expanded = set(queries)
    for word, syns in synonym_map.items():
        if word in low:
            for syn in syns.split():
                if syn not in low:
                    expanded.add(f"{topic} {syn}")
    queries = list(expanded)[:5]  # cap at 5 queries

    seen_sources = {}
    all_rows = []
    for q in queries:
        try:
            rows = hybrid_search.search_hybrid(q, top_k=6)
        except Exception:
            continue
        for r in rows:
            if r["source"] not in seen_sources:
                seen_sources[r["source"]] = r
                all_rows.append(r)

    # 1-hop wikilink expansion: read top-2 files, resolve their wikilinks to vault paths
    neighbor_paths = []
    for r in all_rows[:2]:
        try:
            fp = _resolve_vault_path(r["source"])
            with open(fp, "r", encoding="utf-8") as f:
                links = _wikilinks(f.read())
            for link in links[:5]:
                for cand in _find_by_title(link):
                    if cand not in seen_sources:
                        neighbor_paths.append(cand)
        except Exception:
            continue

    # fetch a chunk from each neighbor
    if neighbor_paths:
        try:
            table = get_db()
            df = table.to_pandas()
        except Exception:
            df = None
        if df is not None:
            for np in neighbor_paths[:4]:
                sub = df[df["source"] == np]
                if len(sub):
                    r = sub.iloc[0].to_dict()
                    r["score"] = 0.05  # neighbor boost floor
                    seen_sources[np] = r
                    all_rows.append(r)

    # trim to char budget
    pkg = []
    used = 0
    for r in all_rows:
        snip = r["text"][:SNIPPET_CHARS]
        if used + len(snip) > budget and pkg:
            break
        pkg.append({
            "source": r["source"],
            "text": snip,
            "score": r.get("score", 0),
            "is_neighbor": r.get("score", 0) == 0.05,
        })
        used += len(snip)

    _log_query("recall", topic, pkg)

    return {
        "topic": topic,
        "count": len(pkg),
        "char_budget": budget,
        "chars_used": used,
        "neighbors_included": sum(1 for p in pkg if p["is_neighbor"]),
        "results": pkg,
    }

def tool_read_vault_sections(params: dict) -> dict:
    """Read only specific '##' sections of a vault file (token-efficient reads)."""
    file_path = params.get("filepath", "")
    sections = params.get("sections", [])  # list of ## header names (case-insensitive substring match)
    if not file_path:
        return {"error": "filepath is required"}

    fp = _resolve_vault_path(file_path)
    try:
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return {"error": f"File not found: {fp}"}
    except Exception as e:
        return {"error": str(e)}

    # split into sections by '## ' headers
    parts = re.split(r"(?m)^(## .+)$", content)
    header = parts[0]
    secs = []
    for i in range(1, len(parts), 2):
        secs.append((parts[i].strip(), parts[i + 1] if i + 1 < len(parts) else ""))

    if sections:
        want = [s.lower() for s in sections]
        picked = [(h, b) for h, b in secs if any(w in h.lower() for w in want)]
        if not picked:
            return {
                "filepath": fp,
                "available_sections": [h.lstrip("# ").strip() for h, _ in secs],
                "note": "no section matched; list provided",
            }
    else:
        # no sections arg -> list available sections only (token-efficient discovery)
        return {
            "filepath": fp,
            "available_sections": [h.lstrip("# ").strip() for h, _ in secs],
            "note": "pass sections=[...] to read specific ones",
        }

    out = "\n\n".join(f"{h}\n{b}".strip() for h, b in picked)
    return {"filepath": fp, "sections": [h.lstrip("# ").strip() for h, _ in picked], "content": out, "size": len(out)}

def tool_get_chunk(params: dict) -> dict:
    source = params.get("source", "")
    if not source:
        return {"error": "source is required"}
    try:
        table = get_db()
        try:
            results = table.search().filter(f"source = '{source}'").limit(50).to_list()
        except Exception:
            df = table.to_pandas()
            filtered = df[df["source"] == source]
            results = filtered.to_dict("records")[:50]
        if results:
            return {
                "source": source,
                "chunks": [{"text": r["text"], "chunk_id": r.get("chunk_id", "")} for r in results],
                "count": len(results),
            }
        return {"error": f"No chunks found for {source}"}
    except Exception as e:
        return {"error": str(e)}

def tool_read_vault_file(params: dict) -> dict:
    file_path = params.get("filepath", params.get("file_path", ""))
    if not file_path:
        return {"error": "filepath is required"}
    fp = _resolve_vault_path(file_path)
    try:
        with open(fp, "r", encoding="utf-8") as f:
            content = f.read()
        return {"filepath": fp, "content": content, "size": len(content)}
    except FileNotFoundError:
        return {"error": f"File not found: {fp}"}
    except Exception as e:
        return {"error": str(e)}

def tool_vault_stats(params: dict) -> dict:
    try:
        table = get_db()
        total = len(table)
        df = table.to_pandas()
        unique_files = df["source"].nunique() if len(df) > 0 else 0
        top_files = df["source"].value_counts().head(15)
        return {
            "total_chunks": total,
            "unique_files": unique_files,
            "db_path": LANCEDB_PATH,
            "embed_model": EMBED_MODEL,
            "ollama_url": OLLAMA_BASE_URL,
            "top_files": [{"file": f, "chunks": int(c)} for f, c in top_files.items()],
        }
    except Exception as e:
        return {"error": str(e)}

def tool_reindex_file(params: dict) -> dict:
    filepath = params.get("filepath", "")
    if not filepath:
        return {"error": "filepath required"}
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    try:
        from vault_indexer import VaultIndexer
        indexer = VaultIndexer()
        n = indexer.index_file(filepath)
        return {"indexed": n, "filepath": filepath}
    except Exception as e:
        return {"error": str(e)}

def tool_index_stats(params: dict) -> dict:
    """Index stats with staleness: hash store vs disk vs chunk count."""
    try:
        import json as _json
        hash_path = Path(HASH_STORE_PATH)
        hashes = {}
        if hash_path.exists():
            with open(hash_path) as f:
                hashes = _json.load(f)
        vault = Path(VAULT_ROOT)
        md_files = [f for f in vault.rglob("*.md")] if vault.exists() else []

        chunk_count = None
        try:
            table = get_db()
            chunk_count = len(table)
        except Exception:
            pass

        # staleness: files on disk not in hash store (approximation of unindexed content)
        disk_set = {str(f) for f in md_files}
        indexed_set = set(hashes.keys())
        stale = len(disk_set - indexed_set)

        return {
            "indexed_files": len(hashes),
            "total_md_files_in_vault": len(md_files),
            "total_chunks": chunk_count,
            "stale_files": stale,
            "db_path": LANCEDB_PATH,
            "status": "ok",
        }
    except Exception as e:
        return {"error": str(e)}

def tool_vault_doctor(params: dict) -> dict:
    """Health report: stale files, duplicate chunks, orphan chunks, query-log usage."""
    try:
        import json as _json
        from collections import Counter

        report = {"generated": datetime.now().isoformat(timespec="seconds")}

        # stale files
        hash_path = Path(HASH_STORE_PATH)
        hashes = {}
        if hash_path.exists():
            with open(hash_path) as f:
                hashes = _json.load(f)
        vault = Path(VAULT_ROOT)
        disk = {str(f) for f in vault.rglob("*.md")} if vault.exists() else set()
        report["index_coverage"] = {
            "indexed": len(hashes),
            "on_disk": len(disk),
            "unindexed_files": len(disk - set(hashes.keys())),
            "deleted_but_still_indexed": len(set(hashes.keys()) - disk),
        }

        # duplicate chunks
        try:
            table = get_db()
            df = table.to_pandas()
            c = Counter(df["chunk_id"])
            dups = {k: v for k, v in c.items() if v > 1}
            report["duplicate_chunks"] = {"ids": len(dups), "extra_rows": sum(v - 1 for v in dups.values())}
        except Exception as e:
            report["duplicate_chunks"] = {"error": str(e)[:100]}

        # orphans: chunks whose source file no longer exists
        try:
            orphan_srcs = [s for s in df["source"].unique() if not Path(s).exists()]
            report["orphan_chunks"] = {"files": len(orphan_srcs)}
        except Exception:
            report["orphan_chunks"] = {"error": "table unavailable"}

        # query log usage (which files get retrieved)
        try:
            qp = Path(QUERY_LOG_PATH)
            usage = Counter()
            n_queries = 0
            if qp.exists():
                with open(qp) as f:
                    for line in f:
                        try:
                            e = _json.loads(line)
                            n_queries += 1
                            for fl in e.get("files", []):
                                usage[fl] += 1
                        except Exception:
                            continue
            report["query_log"] = {
                "queries_logged": n_queries,
                "top_retrieved": [{"file": f, "count": c} for f, c in usage.most_common(10)],
            }
        except Exception:
            report["query_log"] = {"error": "log unavailable"}

        return report
    except Exception as e:
        return {"error": str(e)}

def embed_query(text: str) -> list:
    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": "query: " + text},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()["embedding"]
    except Exception:
        pass
    return []


# ── Tool Definitions (for tools/list) ────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "search_vault",
        "description": (
            "Search the knowledge vault semantically AND by exact tokens (hybrid: "
            "vector + BM25). USE THIS FIRST whenever the user mentions any topic, name, "
            "company, person, project, error, or address that might exist in the vault — "
            "before answering from general knowledge. Exact strings (wallet addresses, "
            "error messages, config values) AND conceptual topics both work. "
            "Arguments: query (str), top_k (int, default 8, max 20). "
            "Returns: chunks with source filepath, fused score, snippet (~800 chars)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — natural language or exact identifier. Examples: 'GGScalping winrate', '0xa70fc67c cashcat', 'lance library is required'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results (default 8, max 20)",
                    "default": 8,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "recall",
        "description": (
            "Assemble a full context package about a topic in ONE call: searches the "
            "topic plus query variants, follows [[wikilinks]] from the top files one hop, "
            "dedupes, and trims to a character budget. Use instead of 3-4 search_vault + "
            "read_vault_file round trips when you need the complete picture of a topic. "
            "Arguments: topic (str), char_budget (int, default 7000)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The topic to assemble context for"},
                "char_budget": {"type": "integer", "description": "Max chars of context returned (default 7000, max 20000)"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "read_vault_file",
        "description": (
            "Read the FULL content of one vault file. Use AFTER search_vault() when a "
            "snippet is not enough. For token efficiency prefer read_vault_sections() "
            "when only part of a file is relevant. "
            "Arguments: filepath (str) — from search results (relative to vault root or absolute)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path from search results"},
            },
            "required": ["filepath"],
        },
    },
    {
        "name": "read_vault_sections",
        "description": (
            "Read ONLY specific '##' sections of a vault file — token-efficient when "
            "a search hit only part of a long file. With no sections arg, returns the "
            "list of available sections. "
            "Arguments: filepath (str), sections (list[str], optional, case-insensitive substring match)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {"type": "string", "description": "Path to vault file"},
                "sections": {"type": "array", "items": {"type": "string"}, "description": "Section names to read (substring match)"},
            },
            "required": ["filepath"],
        },
    },
    {
        "name": "get_chunk",
        "description": "Get all indexed chunks for one source file. Arguments: source (str) — filepath.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source file path"},
            },
            "required": ["source"],
        },
    },
    {
        "name": "vault_stats",
        "description": (
            "Index statistics: total chunks, unique files, top files by chunk count, "
            "model info. Use when checking vault condition."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "reindex_file",
        "description": "Reindex ONE vault file (write op — only on explicit request). Arguments: filepath (str).",
        "inputSchema": {
            "type": "object",
            "properties": {"filepath": {"type": "string", "description": "Full path to reindex"}},
            "required": ["filepath"],
        },
    },
    {
        "name": "index_stats",
        "description": "Index stats with staleness check: indexed files, disk files, chunk count, unindexed files.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "vault_doctor",
        "description": (
            "Vault index health report: coverage (indexed vs on-disk), duplicate chunks, "
            "orphan chunks, and query-log usage (most-retrieved files). Run when search "
            "quality seems off or periodically for hygiene."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]

TOOLS = {
    "search_vault": tool_search_vault,
    "recall": tool_recall,
    "get_chunk": tool_get_chunk,
    "read_vault_file": tool_read_vault_file,
    "read_vault_sections": tool_read_vault_sections,
    "vault_stats": tool_vault_stats,
    "reindex_file": tool_reindex_file,
    "index_stats": tool_index_stats,
    "vault_doctor": tool_vault_doctor,
}

# ── MCP Router ───────────────────────────────────────────────────────────────

def handle_request(req: dict) -> dict:
    method = req.get("method", "")
    params = req.get("params", {})
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "semantic-vault", "version": "2.0.0"},
            },
        }

    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOL_DEFINITIONS}}

    elif method == "tools/call":
        name = params.get("name", "")
        tool_params = params.get("arguments", {})
        if name in TOOLS:
            try:
                result = TOOLS[name](tool_params)
            except Exception as e:
                result = {"error": f"{type(e).__name__}: {e}"}
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]},
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown tool: {name}"},
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    log.info("Semantic Vault MCP server v2 ready")
    while True:
        req = read_request()
        if req is None:
            break
        resp = handle_request(req)
        write_response(resp)

from vault_release_handlers import install as install_release_handlers
install_release_handlers(sys.modules[__name__])

if __name__ == "__main__":
    main()
