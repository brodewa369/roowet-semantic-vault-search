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

## v2.1 (2026-09-18) — Production Release

### What Changed

| Component | Change |
|---|---|
| Indexer | Full reindex: 167→598 files, 899→4,886 chunks. Excludes: .obsidian, .trash, .git, __pycache__ |
| `search_vault()` | Hybrid BM25+vector RRF, folder routing, lesson-learned filter, title boost |
| `recall()` | New — multi-file context expansion (seeds → wikilinks → siblings), pagination, provenance |
| `search_by_tag()` | Tag-specificity sort (fewer tags = more specific first) |
| `search_by_date()` | Date range parsing, daily-note priority |
| Folder routing | "dimana file X", "cron aktif" → morning-brief, "blocked" → blockers |
| Multi-file recall | Snapshot-checked pagination, hard budgets (40 files, 1500c/file) |

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Obsidian Vault (.md)                         │
│  /home/dxwx/wiki/  (598 files, 9 top-level folders)                │
│    ├── 00-NOTES/  ├── 01-AGENT-MEMORY/  ├── 02-KNOWLEDGE/          │
│    ├── 03-RESEARCH/  ├── 04-LOGS/  ├── 05-PROJECT/                 │
│    ├── 06-SYSTEM/  ├── 07-INDEX/  └── 08-BRODEWA-HERMES-SYSTEM/    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      vault_indexer.py                                │
│                                                                      │
│  1. Scan vault (rglob *.md, exclude .obsidian/.trash/.git)        │
│  2. MD5 hash → skip unchanged files                                 │
│  3. Chunk by ## headers (parent 800c + child 250c, overlap 64c)     │
│  4. Batch embed via Ollama /api/embed (50 chunks/batch)             │
│  5. Store in LanceDB (chunk_id, source, text, vector[1024])        │
│  6. FTS index for BM25 search                                       │
│                                                                      │
│  Circuit breaker: 5 failures → pause 60s                            │
│  Backup before dedup: ~/.hermes/backups/vault_vectors_*/            │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        LanceDB Store                                 │
│                                                                      │
│  Table: vault_chunks                                                │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │ chunk_id: str (PK)      │ source: str (filepath)           │    │
│  │ text: str (markdown)    │ vector: float[1024] (bge-m3)    │    │
│  │ indexed_at: str (ISO)   │                                  │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  4,886 chunks from 598 files                                        │
│  FTS index (BM25) for keyword search                               │
│  Hash store: filepath → MD5(content)                                │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                vault_search_hardened.py + vault_search_candidate.py   │
│                                                                      │
│  Query → Intent Detection → Route:                                  │
│    ├─ "dimana file X"?       → folder_page(X)                      │
│    ├─ "cron aktif"?          → folder_page(04-LOGS/morning-brief/) │
│    ├─ "blocked"?             → folder_page(01-AGENT-MEMORY/blockers/)│
│    ├─ tag query?             → metadata_page(tags, sort by specificity)│
│    ├─ date query?            → metadata_page(date, daily-note priority)│
│    ├─ "lesson learned"?      → FTS+Vector → filter lessons-learned/ │
│    └─ general query?         → Hybrid search:                       │
│        1. FTS (BM25) → top-60, weight 0.4                          │
│        2. Vector (cosine) → top-60, weight 0.6                     │
│        3. RRF fusion → combined ranking                            │
│        4. Title boost (0.5x per matching word)                     │
│        5. Dedup by source file                                     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        MCP Tools                                     │
│                                                                      │
│  search_vault(query, top_k=15) → ranked semantic search             │
│  search_by_tag(tags, limit=20) → metadata filter by tags            │
│  search_by_date(date, limit=20) → metadata filter by date           │
│  recall(topic, char_budget=7000, top_k=20) → multi-file expansion   │
│  read_vault_file(filepath) → full file content                      │
│  vault_stats() → index statistics                                    │
│  get_chunk(source) → all chunks for one file                        │
│  reindex_file(filepath) → re-index single file                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Multi-File Recall

```
recall("crypto bot ggscalping wallet tracking", char_budget=7000)

1. Seeds = search_vault results (ranked)
2. Expansion rounds:
   - Round 1: Exact one-hop [[wikilinks]] from seeds
   - Round 2: Cluster siblings (≥2 seeds in same project folder)
3. Hard budgets:
   - MAX_FILES = 40
   - MIN_EXCERPT = 250 chars
   - MAX_FILE_TOPUP = 1500 chars
4. Provenance: seed/sibling/neighbor labels
5. Pagination: snapshot-checked, offset-based
   - omitted_sources / partial_sources / unresolved_links reported
```

## Benchmark Results

| Metric | Original (21q) | Expanded (49q) |
|--------|----------------|----------------|
| Hit@1 | 0.905 | 0.735 |
| Hit@3 | 0.952 | **0.898** ✅ |
| Hit@5 | **1.000** | **0.959** ✅ |
| MRR | 0.940 | 0.828 |

**Root cause fix:** 73% of vault files were not indexed (167→598 files, 899→4,886 chunks).

**Fixes applied:**
- Title boost (filename matching for query relevance)
- Folder routing (location/status queries)
- Post-fusion filter (lesson-learned queries)
- Bilingual aliases (Indonesian-English matching)
- Tag-specificity sorting (fewer tags = more specific)

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
