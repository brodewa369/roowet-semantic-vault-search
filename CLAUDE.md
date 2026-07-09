# CLAUDE.md — Agent Identity & Workflow (Template)

> **FUNGSI:** File ini untuk **Claude / Claude Code / Claude Desktop**.
> Isi SAMA dengan `SOUL.md` (template agent-identity), hanya fungsi beda: SOUL.md untuk agent non-Claude (Hermes/Codex/OpenClaw/OpenCode), CLAUDE.md untuk Claude.
> Technical project context (MCP setup, indexer commands) ada di `AGENTS.md`.

> Template untuk agent AI yang menggunakan Semantic Vault MCP.
> Copy ke project root agent kamu (Claude Code: `CLAUDE.md`). Sesuaikan identity, tone, preferences.

---



## Identity

[Ganti dengan deskripsi agent kamu — siapa, what they do, communication style]

## MANDATORY ON EVERY SESSION START

**THIS RUNS AUTOMATICALLY ON EVERY NEW SESSION. Execute before ANY response.**

### Step-by-step:

1. **`search_vault()`** — semantic context retrieval
   - Query: `"vault structure agent memory error log decisions"`
   - Returns: top-10 relevant chunks
   - Ini menggantikan read_file() untuk file besar

2. **`read_vault_file()`** — jika search result butuh konteks penuh
   - Baca file spesifik dari hasil search_vault

3. **`search_vault()`** — cek error patterns
   - Query: `"error patterns known issues fixes"`

4. **`skills_list()`** — scan semua skill yang available

5. **`search_vault()`** — cek lessons learned
   - Query: `"lessons learned improvements corrections"`

### Verification Standard

Before reporting ANY task as done:

1. **Restate the original scope** — list every item separately
2. **For each item, produce real proof — not a claim:**
   - File created? → `ls` / `cat`, show actual content
   - Function added? → grep for it, or run the test
   - Bug fixed? → reproduce original failure, show it's gone
3. **Paste the command + actual output** in the report
4. **Any item not verified → say so explicitly** as UNVERIFIED
5. **Vault compliance — before reporting done, verify:**
   - Error/bug task? → `error-log/` file must exist
   - Decision made? → `decisions/` file must exist
   - Correction received? → `corrections/` file must exist
   - New knowledge? → file in `02-KNOWLEDGE/` or `03-RESEARCH/`

## Autonomy Tiers

### Hard Gate — explicit confirmation required
- Moving, entering, exiting, or sizing live funds
- Signing or broadcasting any onchain transaction
- Production deploys or prod config changes
- Deleting or overwriting anything without undo path
- Sending messages to real people or public channels
- Changing credentials, API keys, or security settings

### Default Autonomy — move without asking
- Research, drafting, analysis, calculations, dry runs
- Writing or refactoring non-prod code, local testing
- Read-only data pulls, log inspection
- Anything reversible with a clear undo path

## Vault-First Responses

Ketika user nanya tentang APAPUN yang mungkin ada di vault:

```
User: "Apa yang kita punya tentang [topik]?"
Agent: [panggil search_vault("[topik]") → dapat relevant chunks → jawab dari vault]
```

**Jangan jawab dari training data** kalau topiknya spesifik tentang project/user setup.
Selalu `search_vault()` dulu.

## Output Rules

1. **Agent writes directly to destination folder** — no landing zone
2. **NEVER create folders or subfolders.** If no folder fits, use `00-NOTES/` with `#needs-routing`
3. **One topic per file.** Never combine multiple topics.
4. **Never overwrite.** Use `-v2` suffix if filename exists.
5. **Never delete** without explicit user confirmation.
6. **Daily note** required after every task.

## Related Notes

- [[CLAUDE.md]] — Agent project guidance
- [[AGENTS.md]] — Hermes integration
- [[vault-structure/06-SYSTEM/rules/naming-convention]] — File naming
- [[vault-structure/06-SYSTEM/rules/routing-table]] — Where to write what
- [[vault-structure/06-SYSTEM/templates/template-moc]] — MOC creation
