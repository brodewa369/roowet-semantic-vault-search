# Naming Convention

## General Rule
```
lowercase-with-dashes.md
```

## Time-Based Content (use date prefix)
For content tied to a specific time — logs, sessions, errors, mistakes, decisions, daily notes:
```
YYYY-MM-DD-topic-name.md
```
Examples:
- `2026-06-07-bitcoin-analysis.md` — analysis done on that date
- `2026-06-07-vault-rebuild-error.md` — error on that date
- `2026-06-07-trading-decision.md` — decision on that date

## Evergreen Content (no date prefix)
For timeless content — concepts, facts, entities, tools, resources, prompts:
```
concept-name.md
```
Examples:
- `zero-knowledge-proofs.md` — concept
- `solana-wallet-scanner.md` — tool
- `attention-as-resource.md` — permanent note

## Project Content (no date prefix)
```
project-name.md
```

## Content Type → Folder Mapping

| Type | Format | Folder | Example |
|------|--------|--------|---------|
| Error Log | `YYYY-MM-DD-error-name.md` | `error-log/` | `2026-06-07-api-error.md` |
| Decision | `YYYY-MM-DD-decision-name.md` | `decisions/` | `2026-06-07-decision-name.md` |
| Concept | `concept-name.md` | `concepts/` | `zero-knowledge-proofs.md` |
| Fact | `fact-name.md` | `facts/` | `solana-tps-record.md` |
| Entity | `entity-name.md` | `entities/` | `vitalik-buterin.md` |
| Tool | `tool-name.md` | `tools/` | `wallet-scanner.md` |
| Resource | `resource-name.md` | `resources/` | `how-to-build-second-brain.md` |
| Project | `project-name.md` | `projects/` | `ggscalping-overview.md` |
| MOC | `MOC-topic.md` | `index/` | `MOC-crypto.md` |
| Daily Note | `YYYY-MM-DD.md` | `daily-note/` | `2026-06-07.md` |

## Frontmatter (required in every note)
```yaml
---
type: [log/research/knowledge/memory/project/review/error/decision/moc]
status: [active/complete/archived/draft]
date: YYYY-MM-DD
tags: [tag1, tag2]
---
```

## Tag System

### Topic Tags (no prefix)
```
[crypto] [ai] [solana] [trading] [defi] [agent]
```

### Status Tags (prefix `status/`)
```
[status/active] [status/complete] [status/archived]
```

### Type Tags (prefix `type/`)
```
[type/concept] [type/error] [type/decision]
```

### Tag Rules
1. Minimal 2 tags per note (1 topic + 1 status/type)
2. Maksimal 5 tags per note
3. Tag lowercase, multi-word pakai strip
4. Konsisten — cek existing tags sebelum bikin baru
