# MOC (Map of Content) — Agent Instructions

> How to create Maps of Content using the semantic vault.
> Trigger: user says "bikin MOC" or "buat MOC" or "buat index untuk [topic]".

## What is a MOC?

A Map of Content is a **navigation hub** — a single note that links to all notes about a specific topic. Think of it as a curated table of contents.

## When to Create a MOC

Buat MOC ketika:
- Satu folder memiliki 5+ file individual
- Satu topic tersebar di 2+ folder
- User explicit minta MOC
- Topic aktif dan sering diakses (walaupun kurang dari 5 files)

## Step-by-Step

### 1. Search the Vault

```python
# Cari semantic content yang related ke topic
search_vault("topic yang diminta", top_k=20)
```

### 2. Read and Categorize

Dari hasil search:
- Baca judul dan deskripsi tiap file
- Kelompokkan ke 2-4 kategori
- Catat hubungan antar file

### 3. Create MOC File

Gunakan template:

```markdown
---
type: moc
status: active
date: YYYY-MM-DD
tags: [moc, index, TOPIC]
---

# TOPIC — Map of Content

> Brief description of what this MOC covers.

## Category 1
- [[file-1]] — Satu kalimat tentang isi file ini
- [[file-2]] — Satu kalimat tentang isi file ini

## Category 2
- [[file-3]] — Deskripsi singkat

## Related MOCs
- [[MOC-Related]] — Kenapa ini related

## Recent Updates
- YYYY-MM-DD — MOC created
```

### 4. Comparison with RAG

Using the semantic vault:
- `search_vault()` finds relevant files across the entire vault
- You don't need to memorize folder locations
- The search returns files even if they're in unexpected folders
- Cross-reference: run `search_vault()` with the topic from different angles

### 5. Save and Link

1. Save file ke `07-INDEX/MOC-[topic].md`
2. Update `07-INDEX/vault-index.md` with the new MOC link
3. Add `## Related` section with 1-2 wikilinks

## MOC Rules

1. Setiap entry WAJIB punya `[[wikilink]]` + deskripsi. NO bare text.
2. Group by category — jangan dump semua file dalam satu list.
3. WAJIB: Related MOCs section — link ke MOC lain yang relevan.
4. WAJIB: Recent Updates — timestamp setiap perubahan.
5. Gunakan display wikilink: `[[target|display]]` kalau target name beda.
6. Boleh tambah tabel stats kalau membantu (file count, status).
7. JANGAN buat section kosong — skip aja.
8. JANGAN link templates atau vault-rules files.
9. Update MOC setiap kali ada file baru masuk ke folder yang punya MOC.

## Example

User: "bikin MOC untuk crypto"

Agent:
1. `search_vault("crypto trading defi solana", top_k=20)` → 20 results
2. Reads summaries, categorizes: Trading Strategies, DeFi Protocols, Tools
3. Creates `07-INDEX/MOC-crypto.md` with 3 categories
4. Updates `vault-index.md`
