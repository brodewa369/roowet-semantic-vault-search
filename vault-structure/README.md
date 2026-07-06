# Vault Structure — Markdown Knowledge Base Layout

> Example vault structure designed to work with the Semantic Vault MCP.
> The RAG indexes `.md` files by content, not by folder — any structure works.
> This one is optimized for AI-agent-assisted knowledge management.

## Folder Layout

```
vault/
├── 00-NOTES/              ← Staging: unprocessed captures, quick notes
├── 01-AGENT-MEMORY/       ← Agent learning & memory
│   ├── blockers/
│   ├── corrections/
│   ├── decisions/
│   ├── error-log/
│   ├── knowledge-gaps/
│   ├── lessons-learned/
│   ├── patterns/
│   ├── prompts/
│   ├── skills/
│   ├── skill-usage/
│   └── tools/
├── 02-KNOWLEDGE/          ← Reference material
│   ├── concepts/
│   ├── entities/
│   ├── facts/
│   ├── people/
│   ├── resources/
│   └── topics/
├── 03-RESEARCH/           ← Research outputs
│   ├── analyses/
│   └── comparisons/
├── 04-LOGS/               ← Time-based logs
│   ├── daily-note/
│   ├── session-log/
│   └── weekly-note/
├── 05-PROJECTS/           ← Project management
│   ├── active/
│   └── archive/
├── 06-SYSTEM/             ← System config
│   ├── rules/
│   └── templates/
├── 07-INDEX/              ← Maps of Content (MOC)
└── 08-DOCS/               ← System documentation
```

## How the RAG Uses This

The indexer scans all `.md` files recursively, excluding system dirs.

```
vault_indexer.py:
  → Scan: vault/**/*.md
  → Chunk: by ## headers (512-char, 64 overlap)
  → Embed: Ollama BGE-M3 → 1024-dim vectors
  → Store: LanceDB vault_chunks table
```

When you `search_vault("query")`:
1. Query embedded via Ollama
2. Cosine similarity search against all chunks
3. Top-K results with score + source filepath
4. `read_vault_file(filepath)` gets full context

## Templates

28 note templates in `06-SYSTEM/templates/` folder.
Key templates: concept, decision, error, moc, daily, project.

## Naming, Routing & MOC Creation

See `06-SYSTEM/rules/` folder:
- `naming-convention.md` — Date-prefixed vs evergreen filenames
- `routing-table.md` — Content type → folder mapping
- `moc-creation.md` — How agent creates Maps of Content

## Obsidian Setup

See `obsidian-setup.md` for recommended plugins and configuration.

## Quick Start

```bash
# Copy entire vault structure to your location
cp -r vault-structure /path/to/my-vault

# Edit .env: VAULT_ROOT=/path/to/my-vault

# Index
python indexer/vault_indexer.py --once
```
