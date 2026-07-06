#!/usr/bin/env python3
"""
semantic_search_mcp.py — MCP Server for Obsidian Vault Semantic Search
Provides tools:
- search_vault(query, top_k) → semantically search vault chunks
- get_chunk(source, chunk_id) → get full chunk content
- read_vault_file(filepath) → read full file content from vault
- vault_stats() → show vault statistics (total chunks, unique files, top files)
- reindex_file(filepath) → reindex a specific file
- index_stats() → show index statistics
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Deferred imports — lancedb imported only when needed (avoids pylance import bug on Windows)
# try:
#     import lancedb
#     import requests
# except ImportError as e:
#     print(f"Missing dependency: {e}", file=sys.stderr)
#     sys.exit(1)
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

# ── MCP Protocol (stdio) ────────────────────────────────────────────────────

def read_request():
    """Read JSON-RPC request from stdin."""
    line = sys.stdin.readline()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None

def write_response(response):
    """Write JSON-RPC response to stdout."""
    print(json.dumps(response), flush=True)

# ── Tools ────────────────────────────────────────────────────────────────────

def get_db():
    import lancedb  # Deferred import to avoid pylance bug on Windows
    db = lancedb.connect(LANCEDB_PATH)
    return db.open_table("vault_chunks")

def embed_query(text: str) -> list:
    try:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()["embedding"]
    except Exception:
        pass
    return []

def tool_search_vault(params: dict) -> dict:
    """Search vault secara semantic menggunakan Ollama embedding + LanceDB cosine similarity."""
    query = params.get("query", "")
    top_k = min(max(params.get("top_k", 5), 1), 20)

    if not query:
        return {"error": "query is required"}

    vec = embed_query(query)
    if not vec:
        return {"error": "Embedding failed. Is Ollama running?"}

    try:
        table = get_db()
        results = table.search(vec).limit(top_k).to_list()
        return {
            "results": [
                {
                    "source": r["source"],
                    "text": r["text"],
                    "score": r.get("_distance", 0),
                    "chunk_id": r.get("chunk_id", ""),
                }
                for r in results
            ],
            "count": len(results),
            "total_chunks": len(table),
            "query": query,
        }
    except Exception as e:
        return {"error": str(e)}

def tool_get_chunk(params: dict) -> dict:
    """Get all chunks for a specific source file."""
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
    """Baca full content dari satu file di vault. Supports both absolute and relative paths."""
    file_path = params.get("filepath", params.get("file_path", ""))
    if not file_path:
        return {"error": "filepath is required"}

    # Resolve relative paths against VAULT_ROOT root
    p = Path(file_path)
    if not p.is_absolute():
        file_path = str(Path(VAULT_ROOT) / file_path)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"filepath": file_path, "content": content, "size": len(content)}
    except FileNotFoundError:
        return {"error": f"File not found: {file_path}"}
    except Exception as e:
        return {"error": str(e)}

def tool_vault_stats(params: dict) -> dict:
    """Lihat statistik lengkap vault: total chunks, unique files, top files."""
    try:
        table = get_db()
        total = len(table)
        df = table.to_pandas()
        unique_files = df["source"].nunique() if len(df) > 0 else 0

        top_files = df["source"].value_counts().head(15)
        top_list = [{"file": f, "chunks": int(c)} for f, c in top_files.items()]

        return {
            "total_chunks": total,
            "unique_files": unique_files,
            "db_path": LANCEDB_PATH,
            "embed_model": EMBED_MODEL,
            "ollama_url": OLLAMA_BASE_URL,
            "top_files": top_list,
        }
    except Exception as e:
        return {"error": str(e)}

def tool_reindex_file(params: dict) -> dict:
    """Reindex a specific file in the vault."""
    filepath = params.get("filepath", "")
    if not filepath:
        return {"error": "filepath required"}

    script_dir = Path(__file__).parent
    indexer_path = script_dir / "vault_indexer.py"
    if not indexer_path.exists():
        return {"error": f"vault_indexer.py not found at {indexer_path}"}

    sys.path.insert(0, str(indexer_path.parent))
    try:
        from vault_indexer import VaultIndexer
        indexer = VaultIndexer()
        n = indexer.index_file(filepath)
        return {"indexed": n, "filepath": filepath}
    except Exception as e:
        return {"error": str(e)}

def tool_index_stats(params: dict) -> dict:
    """Show index statistics — read from hash store only, no lancedb import at all."""
    try:
        import json
        from pathlib import Path
        
        # Read hash store (always works)
        hash_path = Path(HASH_STORE_PATH)
        hashes = {}
        if hash_path.exists():
            with open(hash_path, "r") as f:
                hashes = json.load(f)
        
        # Count .md files in vault for comparison
        vault = Path(VAULT_ROOT)
        md_files = list(vault.rglob("*.md")) if vault.exists() else []
        
        return {
            "indexed_files": len(hashes),
            "total_md_files_in_vault": len(md_files),
            "db_path": LANCEDB_PATH,
            "status": "ok (hash-store-only)",
            "note": "table count unavailable — lancedb/vault_indexer import triggers pylance bug",
        }
    except Exception as e:
        return {"error": str(e)}


# ── Tool Definitions (for tools/list) ────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "search_vault",
        "description": (
            "Search vault secara semantic. "
            "PAKAI INI sebelum menjawab pertanyaan tentang trading setup, error, project, DeFi, tools, atau apapun yang mungkin ada di vault. "
            "Arguments: query (str), top_k (int, default 5, max 20). "
            "Returns: list of chunks dengan source filepath, similarity score, dan content snippet."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query dalam natural language atau keywords. Contoh: 'DeFi exploit patterns', 'rate limit error', 'vault structure'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Jumlah hasil yang diinginkan (default 5, max 20)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_vault_file",
        "description": (
            "Baca full content dari satu file di vault. "
            "PAKAI INI setelah search_vault() kalau butuh konteks lebih dari snippet. "
            "Arguments: filepath (str) — dapat dari hasil search_vault."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Full path ke file di vault. Dapat dari hasil search_vault(). Contoh: ./vault/02-KNOWLEDGE/concepts/ggscalping-v26-complete-flow.md"
                },
            },
            "required": ["filepath"],
        },
    },
    {
        "name": "vault_stats",
        "description": (
            "Lihat statistik vault: total chunks, jumlah unique file, top files by chunk count. "
            "PAKAI INI kalau user tanya 'vault lo isinya apa?' atau lo mau cek kondisi vault."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_chunk",
        "description": "Get semua chunks untuk suatu source file. Arguments: source (str) — filepath.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Source file path"
                },
            },
            "required": ["source"],
        },
    },
    {
        "name": "reindex_file",
        "description": (
            "Reindex satu file di vault. "
            "HANYA PAKAI kalau user minta explicit. Write operation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Full path ke file yang mau di-reindex"
                },
            },
            "required": ["filepath"],
        },
    },
    {
        "name": "index_stats",
        "description": "Show index statistics: total chunks, unique files, db path.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

TOOLS = {
    "search_vault": tool_search_vault,
    "get_chunk": tool_get_chunk,
    "read_vault_file": tool_read_vault_file,
    "vault_stats": tool_vault_stats,
    "reindex_file": tool_reindex_file,
    "index_stats": tool_index_stats,
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
                "serverInfo": {
                    "name": "semantic-vault",
                    "version": "1.1.0",
                },
            },
        }

    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOL_DEFINITIONS}}

    elif method == "tools/call":
        name = params.get("name", "")
        tool_params = params.get("arguments", {})
        if name in TOOLS:
            result = TOOLS[name](tool_params)
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
    log.info("Semantic Vault MCP server ready")

    while True:
        req = read_request()
        if req is None:
            break
        resp = handle_request(req)
        write_response(resp)

if __name__ == "__main__":
    main()
