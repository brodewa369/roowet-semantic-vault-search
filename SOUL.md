# SOUL.md — Agent Identity & Workflow (Template)

> **PURPOSE:** This file is for agents OUTSIDE Claude Code — e.g. **Hermes, Codex, OpenClaw, OpenCode**, etc.
> Copy to your agent's project root (Hermes: `SOUL.md`). Adjust identity, tone, preferences.
> For Claude / Claude Code, use `CLAUDE.md` (SAME content, different purpose).

> Template for an AI agent using the Semantic Vault MCP.
> Copy to your agent's project root. Adjust identity, tone, and preferences to your needs.

---

## Identity

[Replace with your agent description — who, what they do, communication style]

## MANDATORY ON EVERY SESSION START

**THIS RUNS AUTOMATICALLY ON EVERY NEW SESSION. Execute before ANY response.**

### Step-by-step:

1. **`search_vault()`** — semantic context retrieval
   - Query: `"vault structure agent memory error log decisions"`
   - Returns: top-10 relevant chunks
   - Replaces read_file() for large files

2. **`read_vault_file()`** — if search result needs full context
   - Read specific file from search_vault result

3. **`search_vault()`** — check error patterns
   - Query: `"error patterns known issues fixes"`

4. **`skills_list()`** — scan all available skills

5. **`search_vault()`** — check lessons learned
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

## Vault-First Query Flow (Stage 5 Classification)

Before answering any user query, the agent MUST classify whether vault context is needed:

```
User query / task
      │
      ▼
Stage 5: "Does this need detail from the vault?"
      │
      ├── NO (SIMPLE: general knowledge, chit-chat) ──► Answer directly (1–3 tool calls, no vault)
      │
      └── YES (MEDIUM/COMPLEX: project, error, config, tools, DeFi, etc.)
              │
              ▼
          search_vault(query, top_k=5)
              │
              ├── Relevant chunks found ──► Read context (read_vault_file if needed)
              │                              + Holographic Memory + prior session
              │                              ──► Execute ──► Answer
              │
              └── None / score < 0.5 ──► Answer from own knowledge
                                            (state "not found in vault")
```

**Rules:**
- For queries about project status, past errors, design decisions, concepts, tools, or user preferences → ALWAYS `search_vault()` first (do not answer from training data).
- Do NOT skip the "NO" branch — simple queries do not need vault lookup.
- Web search is FALLBACK only when the vault is empty or the info is newer than what is stored.

## Output Rules

1. **Agent writes directly to destination folder** — no landing zone
2. **NEVER create folders or subfolders.** If no folder fits, use `00-NOTES/` with `#needs-routing`
3. **One topic per file.** Never combine multiple topics.
4. **Never overwrite.** Use `-v2` suffix if filename exists.
5. **Never delete** without explicit user confirmation.
6. **Daily note** required after every task.

## Tag Selection Protocol (MANDATORY BEFORE WRITING)

```
1. search_vault([topic]) → find related notes
2. Extract tags from related notes (REUSE, do not create new)
3. Check existing MOCs for tag convention
4. Use prefixed tags: [status/X], [type/X], [project/X]
5. Max 5 tags: 1 topic + 1 status + 1 type + optional project
6. If a tag is used only once → MERGE into existing tag
```

## Backlink Protocol (MANDATORY BEFORE WRITING)

```
1. search_vault([topic]) → find semantically related notes
2. For each related note → add backlink to new note
3. Update ## Related section existing notes with link to new file
4. Link MUST be relevant — no random links just because "same tag"
5. Target: min 1-2 backlinks per note, max 5
```

## Real-time Logging — HARD GATE

**AGENT-INITIATED:** runs automatically EVERY task completion, without user request.

After EVERY task complete (skip for small talk/greeting/cancelled task), BEFORE reporting "done" to user:

1. **Check Pre-Response Vault Check table** — write file to appropriate folder (error-log, decisions, patterns, etc.)
2. **Append entry to daily note** `04-LOGS/daily-note/YYYY-MM-DD.md`
3. **Check and fill if relevant:** `decisions/`, `error-log/`, `patterns/`, `lessons-learned/`, `knowledge-gaps/`, `skill-usage/`, `02-KNOWLEDGE/entities|concepts|facts|resources/`, `01-AGENT-MEMORY/tools/`
4. **ls destination folder** — verify file actually exists
5. Failed write → tell user, never silently skip

## Related Notes

- [[CLAUDE.md]] — Agent project guidance
- [[AGENTS.md]] — Hermes integration
- [[vault-structure/06-SYSTEM/rules/naming-convention]] — File naming
- [[vault-structure/06-SYSTEM/rules/routing-table]] — Where to write what
- [[vault-structure/06-SYSTEM/templates/template-moc]] — MOC creation
- [[vault-structure/06-SYSTEM/rules/agent-tagging-backlink-rules]] — Tag & backlink rules