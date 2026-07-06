# CLAUDE.md — Semantic Vault MCP

> Project context for Claude Code / Claude Desktop.
> When working in or with this project, the MCP server `semantic-vault` provides tools for semantic search over markdown vaults.

---

## What This Project Does

This is a **local RAG system** for markdown vaults (Obsidian, Foam, Dendron, or plain markdown folders):

1. `vault_indexer.py` — scans vault, chunks by headers, embeds via Ollama, stores in LanceDB
2. `mcp_server/server.py` — MCP server that exposes search/read tools to any MCP client (Claude Desktop, Claude Code, Hermes)

## Available MCP Tools

Once the MCP server is registered (see README.md), the following tools become available:

| Tool | What it does | When to use |
|------|-------------|-------------|
| `search_vault(query, top_k=5)` | Semantic search by meaning | User asks about something that lives in the vault (concepts, decisions, errors, notes) |
| `read_vault_file(filepath)` | Read full markdown file | Need more context after search, or user specifies a file path |
| `vault_stats()` | Index statistics | Check how many chunks/files are indexed |
| `get_chunk(source)` | All chunks for one file | Debug indexing or get full breakdown |
| `reindex_file(filepath)` | Re-index a single file | After editing a file outside the watcher |

## How to Use in Conversations

```
User: "What do I have about DeFi exploits?"
Agent: [calls search_vault("DeFi exploit patterns") → gets relevant chunks → answers from vault content]
```

**Priority:** When a user asks about content that likely exists in their vault → ALWAYS call `search_vault()` first before guessing from training data.

## Running the Indexer

```bash
# One-shot full index
python indexer/vault_indexer.py --once

# File watcher daemon
python indexer/vault_indexer.py --watch

# Full re-index (clear all)
python indexer/vault_indexer.py --reindex
```

## Project Structure

```
semantic-vault-mcp/
├── indexer/vault_indexer.py     # Scan → chunk → embed → store
├── mcp_server/server.py         # MCP protocol server
├── vault-structure/         # Example vault layout
│   ├── README.md
│   ├── obsidian-setup.md
│   ├── 00-NOTES/ … 08-DOCS/ # Folder structure
│   ├── 06-SYSTEM/rules/     # Naming, routing, MOC creation
│   ├── 06-SYSTEM/templates/ # 28 note templates
```

## Configuration (via .env)

| Var | Default | Description |
|-----|---------|-------------|
| `VAULT_ROOT` | `./vault` | Path to markdown vault |
| `LANCEDB_PATH` | `./data/lancedb` | Vector store location |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `EMBED_MODEL` | `bge-m3` | Embedding model |
| `EXCLUDE_DIRS` | `.obsidian,.trash,.git` | Folders to skip |
