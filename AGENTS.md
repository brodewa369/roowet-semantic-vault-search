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
### Session Init — WAJIB

1. **search_vault()** — semantic context retrieval
   - Query: `"vault structure agent memory error log decisions lessons learned"`
   - Returns: top-10 relevant chunks (~10-15KB)
   - Ini menggantikan `read_file()` untuk file besar

2. **read_vault_file()** — jika search result butuh konteks penuh
   - Baca file spesifik dari hasil search_vault
   - Contoh: `read_vault_file("path/ke/file.md")`

3. **vault_stats()** — cek kondisi vault
   - Total chunks, unique files, db path
```

---

## Auto Semantic Search Rule

Agent WAJIB call `search_vault()` TANPA perlu user bilang "cari di vault" ketika user nanya tentang:

- Project status dan progress
- Error/bug yang pernah terjadi
- Keputusan desain/arsitektur
- Konsep atau topik yang mungkin ada di vault
- Tools, scripts, atau workflow
- Preferences atau konfigurasi

**Flow:**
```
User asks question → agent calls search_vault(query) 
  → result relevan? → jawab dari vault
  → result kosong? → jawab dari pengetahuan sendiri, bilang "tidak ditemukan di vault"
```

---

## Mid-Session Safety Net

Jika user berganti topik di tengah session:

```markdown
- WAJIB: search_vault() lagi dengan query baru
- BOLEH skip: small talk, lanjutan task yang sama
- Fallback: score < 0.5 → proceed tanpa hasil vault
```

---

## Cron: Auto-Reindex

```yaml
# Reindex vault setiap 6 jam (incremental — hanya file berubah)
name: vault-indexer
schedule: every 6h
script: python indexer/vault_indexer.py --once
no_agent: true
```

---

## Tools Routing Priority

| Situasi | Pake |
|---------|------|
| Cari konten by meaning | `search_vault(query)` ← semantic |
| Baca full file | `read_vault_file(path)` ← dari hasil search |
| Cek statistik index | `vault_stats()` |
| Debug index | `get_chunk(source)` |
| Reindex 1 file | `reindex_file(path)` |
| Full text search / grep | `grep` / `search_files` (fallback) |
