# Routing Rules — Where to Write What

## Based on Content Type

| Type | Destination |
|------|-------------|
| Daily log | `daily-note/` or `session-log/` |
| Error / Mistake | `error-log/` |
| Decision | `decisions/` |
| Research (raw) | `research/analyses/` |
| Research (analyzed) | `research/analyses/` |
| Comparison | `research/comparisons/` |
| Concept / Theory | `concepts/` |
| Fact | `facts/` |
| Person / Entity | `entities/` |
| Tool / MCP | `tools/` |
| Resource | `resources/` |
| Prompt template | `prompts/` |
| Pattern / Insight | `patterns/` |
| Lesson Learned | `lessons-learned/` |
| Skill Usage | `skill-usage/` |
| Project | `projects/` |
| Project Progress | `progress/` |
| MOC / Index | `index/` |

## Based on Topic (for knowledge/research)

| Topic | Folder |
|-------|--------|
| crypto, defi, blockchain | `topics/crypto/` |
| ai, llm, machine learning | `topics/ai/` |
| development, coding | `topics/dev/` |

## Write-Time Linking

Every new note MUST have a `## Related` section with at least 1-2 `[[wikilinks]]`:
- Write links AT THE SAME TIME as writing the note (not batch cleanup later)
- Links must be semantically relevant, not keyword dumps
- If no related file exists, skip (don't force it)

## Hard Rules

1. **Agent NEVER creates folders.** If no existing folder fits, use `00-NOTES/` with `#needs-routing` tag.
2. **One topic per file.** Never combine multiple topics.
3. **Never overwrite.** Use `-v2` suffix if filename exists.
4. **Never delete** files without explicit user confirmation.
5. **Templates** are in `templates/` — read before writing.
6. **Daily note required** after every task.
