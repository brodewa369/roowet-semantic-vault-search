# Vault Tagging & Backlink Guidelines

## Agent Tagging Rules

### 1. Tag Standardization

**ALWAYS use prefixed tags:**

| Category | Prefix | Examples |
|----------|--------|----------|
| Topic | (none) | `[crypto] [ai] [solana]` |
| Status | `status/` | `[status/active] [status/complete]` |
| Type | `type/` | `[type/error] [type/decision]` |
| Project | `project/` | `[project/ggscalping] [project/stokbot]` |

**NEVER use unprefixed variants:**
- ❌ `[active]` → ✅ `[status/active]`
- ❌ `[decision]` → ✅ `[type/decision]`
- ❌ `[error]` → ✅ `[type/error]`
- ❌ `[research]` → ✅ `[type/research]` (if research output) or `[research]` (if research topic)

### 2. Tag Selection

**When creating a new note, follow these steps:**

1. **Read existing notes on similar topics** — use `search_vault()` to find related files
2. **Extract tags from related notes** — reuse their tags when applicable
3. **Limit to 2-5 tags** — 1 topic + 1 status/type + optional project
4. **Avoid single-use tags** — if a tag is only used once, merge it with an existing tag

**Tag priority (in order):**
1. Existing tags from related notes (REUSE)
2. Tags from existing MOCs (follow their convention)
3. New tags ONLY if no existing tag fits

### 3. Tag Co-occurrence Hints

When you see these tags, consider adding related tags:

| If you have... | Consider adding... |
|----------------|-------------------|
| `[project/ggscalping]` | `[crypto] [trading] [bot]` |
| `[project/stokbot]` | `[crypto] [bot] [automation]` |
| `[rag]` | `[ai] [search] [vault]` |
| `[type/error]` | `[agent] [debugging]` |
| `[cron]` | `[automation] [scheduling]` |
| `[kde]` | `[linux] [desktop] [customization]` |
| `[telegram]` | `[bot] [automation] [crypto]` |

## Agent Backlink Rules

### 1. Mandatory ## Related Section

**EVERY note MUST have a `## Related` section with at least 1 link.**

Exception: truly isolated notes (rare — if you can't find any related note, skip this section).

### 2. How to Find Related Notes

1. **Search by tags** — find notes with overlapping tags
2. **Search by topic** — use `search_vault()` to find semantically related notes
3. **Search by project** — if note belongs to a project, link to project LOG.md
4. **Search by date** — link to adjacent daily-notes or same-topic notes

### 3. Backlink Quality

**Each link MUST be relevant — not just "somewhat related".**

Good backlinks:
- Same project
- Same topic, different perspective
- Follow-up or continuation
- Prerequisites or dependencies

Bad backlinks (don't add):
- Same folder but unrelated content
- Same tag but different topic
- Just because they exist

### 4. Update Existing Notes

**When you create a new note related to existing notes, UPDATE those notes to link back.**

Example: If you create `2026-09-18-rag-optimization.md` and it relates to `2026-09-17-rag-benchmark.md`, add to the older note's `## Related`:
```markdown
- [[2026-09-18-rag-optimization]] — follow-up with optimized search
```

## Implementation Checklist

When agent creates a new note:

1. ✅ Frontmatter with valid tags (prefixed, 2-5 tags)
2. ✅ `## Related` section with ≥1 backlinks
3. ✅ Existing notes updated with backlinks to new note
4. ✅ Tags follow existing conventions (no new tags when existing ones fit)
5. ✅ No orphan note (at least 1 inbound or outbound link)

## Anti-patterns (DO NOT)

- ❌ Creating new tags when existing ones fit
- ❌ Using unprefixed status/type tags (`[active]`, `[decision]`)
- ❌ Notes without `## Related` section
- ❌ Notes with empty `## Related` section
- ❌ Backlinks to completely unrelated notes just to satisfy the rule
- ❌ Tags like `[misc]`, `[general]`, `[other]` — be specific
- ❌ More than 5 tags per note
- ❌ Tags that are only used once (eliminate or merge)
