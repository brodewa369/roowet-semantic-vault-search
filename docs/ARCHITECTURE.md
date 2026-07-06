# Architecture — Semantic Vault MCP

## Data Flow

```
                    ┌──────────────────────────────────────┐
                    │         Obsidian Vault (.md)         │
                    │  C:/Users/you/wiki/                  │
                    │    ├── 01-AGENT-MEMORY/              │
                    │    ├── 02-KNOWLEDGE/                 │
                    │    ├── 03-RESEARCH/                  │
                    │    └── ...                           │
                    └──────────────┬───────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────────┐
                    │        vault_indexer.py              │
                    │                                      │
                    │  1. Scan vault for .md files         │
                    │  2. Chunk by ## headers              │
                    │  3. Batch embed via Ollama           │
                    │  4. Store vectors in LanceDB         │
                    │                                      │
                    │  ┌──────────────────────────────┐    │
                    │  │ Exclude dirs: .obsidian,     │    │
                    │  │ .trash, .git, __pycache__    │    │
                    │  └──────────────────────────────┘    │
                    └──────────────┬───────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────┐
                    │          LanceDB Store               │
                    │                                      │
                    │  vault_chunks.lance                  │
                    │  ┌──────────────────────────────┐    │
                    │  │ chunk_id: str (PK)           │    │
                    │  │ source: str (filepath)       │    │
                    │  │ text: str (markdown content) │    │
                    │  │ vector: float[1024]          │    │
                    │  │ indexed_at: str (ISO)        │    │
                    │  └──────────────────────────────┘    │
                    │                                      │
                    │  Hash store (JSON):                  │
                    │  filepath → MD5(content)             │
                    └──────────────────────────────────────┘
                                   ▲
                                   │
                    ┌──────────────┴───────────────────────┐
                    │    semantic_search_mcp.py (MCP)      │
                    │                                      │
                    │  Tools:                              │
                    │  ├── search_vault(query, top_k)      │
                    │  │    → embed query → LanceDB search │
                    │  │    → return top-k chunks          │
                    │  │                                   │
                    │  ├── read_vault_file(filepath)       │
                    │  │    → read full .md from disk      │
                    │  │                                   │
                    │  ├── vault_stats()                   │
                    │  │    → total chunks, unique files   │
                    │  │                                   │
                    │  ├── get_chunk(source)               │
                    │  │    → all chunks for one file      │
                    │  │                                   │
                    │  └── reindex_file(filepath)          │
                    │       → re-index single file         │
                    └──────────────┬───────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────────────┐
                    │  MCP Client (Claude Desktop /        │
                    │  Hermes / Claude Code)               │
                    │                                      │
                    │  Agent calls search_vault("DeFi      │
                    │  exploit patterns") → gets relevant  │
                    │  chunks → uses as context            │
                    └──────────────────────────────────────┘
```

## Key Design Decisions

### Why LanceDB?
- **No separate service** — embedded vector DB, runs in-process
- **Persistent** — survives restarts
- **Fast** — 10-50ms per query for vault-sized datasets
- **Standard schema** — Lance (columnar) format, inspectable with pandas

### Why Ollama + BGE-M3?
- **100% local** — no API costs, no data leakage
- **Multilingual** — BGE-M3 supports 100+ languages
- **1024d vectors** — good balance of speed vs accuracy
- **Batch embedding** — `/api/embed` endpoint sends 50 texts per call

### Why True Batch Embedding?
Ollama's `/api/embed` accepts multiple texts in one HTTP call:
- Before: 1 HTTP call per chunk → 50 calls for 50 chunks
- After: 1 HTTP call for 50 chunks → **30-50x faster**

### Architecture Pattern: Hybrid Context (init + on-demand)
Rather than loading everything upfront:
1. **Injection**: Always load ~15KB of essential context (rules + memory)
2. **On-demand**: Semantic search for task-specific context
3. **Safety net**: Search again if topic changes mid-session

## Embedding Dimension Migration

If switching models, re-index with `--reindex` flag:

```bash
# nomic-embed-text → bge-m3 (768d → 1024d)
# Edit .env: EMBED_MODEL=bge-m3, EMBED_DIM=1024
python indexer/vault_indexer.py --reindex
```
