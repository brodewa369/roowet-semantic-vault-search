<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
  <img src="https://img.shields.io/badge/Ollama-ready-orange?logo=ollama&logoColor=white" />
  <img src="https://img.shields.io/badge/MCP-server-purple" />
  <img src="https://img.shields.io/badge/LanceDB-vector--db-brightgreen" />
</p>

<p align="center">
  <img src="docs/banner.jpeg" alt="Roowet Semantic Vault Search" width="75%" />
</p>

# Semantic Vault MCP

**Local RAG semantic search for Obsidian vaults — powered by Ollama + LanceDB + MCP.**

Search your markdown vault by **meaning** (not keyword matching). Runs fully local — zero API costs, zero data leaves your machine.

```
User query → Ollama embed → LanceDB vector search → relevant chunks → LLM context
```

## Features

- 🔍 **Semantic search** — find notes by concept, not keyword
- 🚀 **Batch embedding** — 30-50x faster than serial (50 chunks per HTTP call)
- 👁️ **Auto file watcher** — re-index files as they change (via watchdog)
- 🧩 **MCP server** — drop-in tool for Claude Desktop / Claude Code / Hermes
- 💾 **Persistent hash store** — incremental indexing, only re-index what changed
- 🔄 **Crash-safe** — circuit breaker for Ollama, batch writes to LanceDB

## Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com) running locally
- An Obsidian vault (or any markdown folder)

### 1. Install

```bash
# Clone
git clone https://github.com/brodewa369/roowet-semantic-vault-search.git
cd semantic-vault-mcp

# Windows
setup.bat

# Linux/Mac
chmod +x setup.sh && ./setup.sh
```

### 2. Configure

Edit `.env`:

```env
VAULT_ROOT=C:/Users/you/your-obsidian-vault
OLLAMA_BASE_URL=http://localhost:11434
EMBED_MODEL=bge-m3
```

### 3. Index your vault

```bash
python indexer/vault_indexer.py --once
```

### 4. Add MCP to Claude Desktop / Hermes

```json
{
  "mcpServers": {
    "semantic-vault": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "VAULT_ROOT": "C:/Users/you/your-vault",
        "LANCEDB_PATH": "./data/lancedb",
        "OLLAMA_BASE_URL": "http://localhost:11434",
        "EMBED_MODEL": "bge-m3"
      }
    }
  }
}
```

Restart Claude Desktop. You now have `search_vault()`, `read_vault_file()`, `vault_stats()` in your agent's toolbelt.

## Architecture

```
┌──────────────┐    ┌─────────────────────┐    ┌──────────────────────┐
│              │    │  vault_indexer.py   │    │  semantic_search_    │
│  Obsidian    │───▶│                     │───▶│  mcp.py (MCP server) │
│  Vault (.md) │    │  - scan vault       │    │                      │
│              │    │  - chunk by ##      │    │  Tools:              │
└──────────────┘    │  - embed (Ollama)   │    │  - search_vault()    │
                    │  - store (LanceDB)  │    │  - read_vault_file() │
                    └──────────┬──────────┘    │  - vault_stats()     │
                               │               │  - get_chunk()       │
                               ▼               │  - reindex_file()    │
                    ┌─────────────────────┐    │  - index_stats()     │
                    │     LanceDB         │    └──────────────────────┘
                    │  vault_chunks.lance │              │
                    │  (vector store)     │              ▼
                    └─────────────────────┘    ┌──────────────────────┐
                                               │  Claude Desktop /    │
                                               │  Hermes / Claude Code│
                                               │  (MCP client)        │
                                               └──────────────────────┘
```

## Commands

| Command | Description |
|---------|-------------|
| `python indexer/vault_indexer.py --once` | Index all vault files once |
| `python indexer/vault_indexer.py --watch` | Run as file watcher daemon |
| `python indexer/vault_indexer.py --reindex` | Clear and re-index everything |
| `python -m mcp_server.server` | Start MCP server (stdio transport) |

## MCP Tools

| Tool | Description |
|------|-------------|
| `search_vault(query, top_k=5)` | Semantic search by meaning |
| `read_vault_file(filepath)` | Read full file content |
| `vault_stats()` | Index statistics |
| `get_chunk(source)` | Get all chunks for a file |
| `reindex_file(filepath)` | Re-index a specific file |
| `index_stats()` | Hash-store statistics |

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VAULT_ROOT` | ✅ | `./vault` | Path to markdown vault |
| `LANCEDB_PATH` | ✅ | `./data/lancedb` | Vector store path |
| `OLLAMA_BASE_URL` | ✅ | `http://localhost:11434` | Ollama endpoint |
| `EMBED_MODEL` | ✅ | `bge-m3` | Embedding model |
| `EMBED_DIM` | ❌ | `1024` | Embedding dimensions |
| `CHUNK_SIZE` | ❌ | `512` | Chunk size (chars) |
| `OVERLAP` | ❌ | `64` | Chunk overlap |
| `BATCH_SIZE` | ❌ | `50` | Embedding batch size |
| `EXCLUDE_DIRS` | ❌ | `.obsidian,.trash,.git` | Folders to skip |
| `MAX_BACKUPS` | ❌ | `2` | Backup retention |

## Project Structure

```
semantic-vault-mcp/
├── README.md               # Quick start + MCP config
├── CLAUDE.md               # Agent identity template — FUNGSI: Claude / Claude Code
├── AGENTS.md               # Technical MCP context + Hermes integration
├── SOUL.md                 # Agent identity template — FUNGSI: agent non-Claude (Hermes/Codex/OpenClaw/OpenCode)
├── skills/                 # Agent skills (jalankan via /nama-skill)
│   └── scanthissession/    # Scan session → tulis ke vault (error/decision/correction/dll)
├── LICENSE                 # MIT
├── pyproject.toml          # pip install .
├── requirements.txt
├── .env.example            # All 12 env vars documented
├── .gitignore
├── setup.bat               # Windows one-click setup
├── setup.sh                # Linux/Mac one-click setup
├── indexer/
│   ├── __init__.py
│   └── vault_indexer.py    # Scan → chunk → embed → store
├── mcp_server/
│   ├── __init__.py
│   └── server.py           # MCP protocol server
├── vault-structure/         # Example vault layout
│   ├── README.md           # Folder structure explained
│   ├── obsidian-setup.md   # Recommended Obsidian plugins
│   ├── 00-NOTES/ … 08-DOCS/ # 30+ empty folders
│   ├── 06-SYSTEM/rules/    # Naming, routing, MOC creation
│   └── 06-SYSTEM/templates/ # 28 note templates
└── docs/
    └── ARCHITECTURE.md     # Data flow + design decisions
```

## Requirements

- **Ollama** with any embedding model (tested: `bge-m3`, `nomic-embed-text`)
- Python packages: `lancedb`, `pyarrow`, `requests`, `watchdog`
- ~2GB RAM for LanceDB (depends on vault size)

## Keeping Your Index Fresh

**Why regular indexing matters:**

The RAG search is only as good as your index. If you add/edit 50 files but haven't re-indexed, the search will return **stale chunks** — or miss new content entirely.

The indexer uses MD5 content hashes to detect changes, so re-indexing is fast:
```bash
# Incremental — only processes changed files (usually <1 second)
python indexer/vault_indexer.py --once
```

**Recommended cadence:**
- **Manual:** Run `--once` after any significant vault edit session
- **Cron:** Auto-index every 6 hours (the indexer is idempotent)
- **Watch mode:** `--watch` for real-time indexing (runs as daemon)

When in doubt: **re-index before every AI agent session.** A 1-second re-index can save you from getting answers based on stale vault content.

## FAQ

**Q: How long does initial indexing take?**
A: ~30-60s for 100 files with bge-m3. Batch embedding does 50 chunks per call.

**Q: Can I use other embedding models?**
A: Yes. Set `EMBED_MODEL` and `EMBED_DIM` in `.env`. Tested with `bge-m3` (1024d) and `nomic-embed-text` (768d).

**Q: Does it support incremental updates?**
A: Yes. Indexer tracks file content hashes (MD5). Re-run `--once` to only index changed files.

**Q: Can I use this without Obsidian?**
A: Yes. Any folder with `.md` files works. Set `VAULT_ROOT` to any markdown directory.

## License

MIT
