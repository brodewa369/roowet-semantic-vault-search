---
name: claim-update-gate
description: Use when writing a stateful vault fact — update the owner.
version: 1.0.0
author: Owi (Brodewa)
license: MIT
metadata:
  hermes:
    tags: [rag, vault-writing, memory-hygiene]
    related_skills: [vault-management, rag-vault-search]
---

# Claim Update Gate — no dualism in the vault

## When to Use
Before writing ANY stateful claim about a project, tool, or entity to the vault — project state, config state, tool status, entity status. Not for incident logs (those stay dated).

## Why
Benchmark 2026-10-17 (cron topic) proved lexical RAG surfaces stale claims as present-tense truth. Root cause is write-side: the agent creates NEW files for facts that already have an owner file. Two files arguing about the same present-tense fact = dualism noise that ranking cannot fix.

## The gate (run BEFORE every vault write)
1. Classify the claim:
   - **Stateful** — project status, tool/config state, entity state ("stokbot is on Supabase pooler", "cron model is mimo @9rt").
   - **Incident/dated** — error, lesson, decision, daily note ("hit error X on 2026-10-17").
2. STATEFUL claims:
   - `search_vault("<entity/topic>")` first.
   - Owner file exists (project overview, LOG.md, tool note, entity note)? → **UPDATE that file**: append the new claim to its `## History` section with date; never delete prior entries.
   - No owner file → create ONE state file for that entity; it becomes the single owner from now on.
   - Creating a second state file for a fact that has an owner is a violation.
3. INCIDENT/dated claims:
   - New date-stamped file (existing per-type rules).
   - MUST backlink the stateful owner file it changes status of (## Related), AND update that owner file's History with a one-line pointer to the incident file.
4. Never merge multiple entries into one file (existing rule). History section = dated one-liners, not prose blobs.

## Enforcement
- Self-check before reporting done: did this task create any state file whose fact already had an owner? If yes → merge into owner; delete nothing without confirmation.
- Decision record: [[01-AGENT-MEMORY/decisions/2026-10-17-claim-update-protocol-write-gate]]

## Related
- Skills: vault-management, rag-vault-search
