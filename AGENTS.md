# AGENTS.md — Hermes Agent Integration

> For Hermes users: how to wire semantic vault into your agent's init flow.
> Copy relevant sections to your own AGENTS.md / SOUL.md / CLAUDE.md.

---

## MCP Server Config

Add this to your `config.yaml`:

```yaml
semantic-vault:
  args: []
  command: python
  connect_timeout: 30
  env:
    VAULT_ROOT: C:/Users/you/path/to/vault
    LANCEDB_PATH: C:/Users/you/data/lancedb
    OLLAMA_BASE_URL: http://localhost:11434
    EMBED_MODEL: bge-m3
  timeout: 60
  working_directory: C:/Users/you/semantic-vault-mcp
```

> **Windows note:** If `python` doesn't resolve to the right venv, use a `.bat` wrapper:
> ```bat
> @echo off
> call C:\path\to\venv\Scripts\activate.bat
> python -m mcp_server.server %*
> ```

---

## Init Flow Integration

Add these steps to your session init (in SOUL.md or your init protocol):

```markdown
### Session Init — REQUIRED

1. **`search_vault()`** — semantic context retrieval
   - Query: `"vault structure agent memory error log decisions lessons learned"`
   - Returns: top-10 relevant chunks (~10-15KB)
   - Replaces read_file() for large files

2. **`read_vault_file()`** — if search result needs full context
   - Read specific file from search_vault result
   - Example: `read_vault_file("path/to/file.md")`

3. **`vault_stats()`** — check vault condition
   - Total chunks, unique files, db path
```

---

## Query Classification (Stage 5)

Before any vault lookup, the agent MUST classify the query:

- **NO (SIMPLE):** general knowledge, chit-chat, obvious answer → answer directly, no `search_vault()`.
- **YES (MEDIUM/COMPLEX):** project status, past errors, design decisions, concepts, tools, scripts, workflow, user preferences/config → call `search_vault()` without waiting for the user to say "search the vault".

**Flow:**
```
User asks → Stage 5: "Need vault detail?"
  ├── NO → answer directly
  └── YES → search_vault(query)
              → relevant? → answer from vault
              → empty (score < 0.5)? → answer from own knowledge, state "not found in vault"
```

## Mid-Session Topic Switch

When the user changes topic mid-session:
- REQUIRED: `search_vault()` again with a new query
- SKIP allowed: small talk, continuation of the same task
- Fallback: score < 0.5 → proceed without vault result

---

## Vault Maintenance (Weekly/Monthly)

**Weekly (Sunday):**
```bash
# Update folder index.md files (auto-generate)
python scripts/vault_generate_index.py

# Run comprehensive vault health check (9 checks)
python scripts/vault_health_weekly.py

# Run tag audit (single-use tags, orphans, missing backlinks)
python scripts/vault_tag_audit.py
```

**Monthly (1st):**
```bash
# Query log analysis
python3 -c "
from pathlib import Path
log = Path.home() / '.hermes/vault_vectors/query_log.jsonl'
if log.exists():
    lines = log.read_text().strip().splitlines()
    print(f'Total queries: {len(lines)}')
"
```

## Tag & Backlink Rules

**Agent MUST follow these when writing to vault:**

1. **Search before tag** — `search_vault([topic])` → extract tags from related notes → REUSE
2. **Prefixed tags only** — `[status/active]` not `[active]`, `[type/error]` not `[error]`
3. **Max 5 tags** — 1 topic + 1 status + 1 type + optional project
4. **Single-use tags** — merge into existing tag if only used once
5. **Backlinks mandatory** — `## Related` section with ≥1 relevant `[[wikilink]]`
6. **Update existing notes** — when creating new note, add backlink to existing related notes

**See detailed rules: `vault-structure/06-SYSTEM/rules/agent-tagging-backlink-rules.md`**

---

## Tools Routing Priority

| Situation | Use |
|---------|------|
| Find content by meaning | `search_vault(query)` ← semantic |
| Read full file | `read_vault_file(path)` ← from search result |
| Check index stats | `vault_stats()` |
| Debug index | `get_chunk(source)` |
| Reindex one file | `reindex_file(path)` |
| Full text search / grep | `grep` / `search_files` (fallback) |

---

## Technical MCP Context (Project Setup)

> Moved from `CLAUDE.md` so `CLAUDE.md`/`SOUL.md` focus on the agent-identity template.
> Agent-identity rules are in `SOUL.md` (non-Claude) and `CLAUDE.md` (Claude).

### What This Project Does

Local RAG system for markdown vaults (Obsidian/Foam/Dendron/plain md):
1. `vault_indexer.py` — scan vault, chunk by headers, embed via Ollama, store in LanceDB
2. `mcp_server/server.py` — MCP server exposing search/read tools to MCP clients (Claude Desktop, Claude Code, Hermes)

### Available MCP Tools

| Tool | What it does | When to use |
|------|-------------|-------------|
| `search_vault(query, top_k=15)` | Semantic search by meaning | Find content by concept |
| `search_by_tag(tags, limit=20)` | Metadata filter by tags | Filter by specific tags |
| `search_by_date(date, limit=20)` | Metadata filter by date | Find entries from specific dates |
| `recall(topic, char_budget=7000, top_k=20)` | Multi-file context expansion | Broad topic needing many related files |
| `read_vault_file(filepath)` | Read full markdown file | Need full context after search |
| `vault_stats()` | Index statistics | Check index health |
| `get_chunk(source)` | All chunks for one file | Debug indexing |
| `reindex_file(filepath)` | Re-index single file | After editing outside watcher |

### Running the Indexer

```bash
python indexer/vault_indexer.py --once      # one-shot full index
python indexer/vault_indexer.py --watch      # file watcher daemon
python indexer/vault_indexer.py --reindex    # full re-index (clear all)
```

### Configuration (.env)

| Var | Default | Description |
|-----|---------|-------------|
| `VAULT_ROOT` | `./vault` | Path to markdown vault |
| `LANCEDB_PATH` | `./data/lancedb` | Vector store location |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `EMBED_MODEL` | `bge-m3` | Embedding model |
| `EXCLUDE_DIRS` | `.obsidian,.trash,.git` | Folders to skip |
