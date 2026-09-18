---
name: scanthissession
description: Scan current or active session transcript, detect vault-relevant items (topic, blocker, correction, decision, error/bug, knowledge-gap, lesson, pattern, skill-usage, entity, person, topic), then WRITE them to the correct vault folder per rules. Use after a work session, when user says scan session, or before ending a long task. Trigger words scan session, log this session, scanthisession. NOTE: replace `<VAULT_ROOT>` and `<HERMES_SCRIPTS>` with your environment paths before use.
---

# /scanthissession — Session Scanner & Vault Writer

## PURPOSE
LLMs do not automatically log errors/facts when encountered (passive instructions fail). This skill FORCES scan + write via an explicit procedure. When the agent runs this skill, it MUST read the session, classify, and write files.

## WHEN TO RUN
- User: scan session, scan this session, log session ini, /scanthissession
- Or after a complex task (>10 tool calls) → run as cleanup
- Do NOT run mid-task (unless the user asks)

## PROCEDURE (run step by step)

### Step 1 — Get session transcript
- Default profile: `hermes sessions list` → find active session → read via `session_search(session_id=...)`.
- Other profile: `hermes -p <profile> sessions list` then `session_search`.
- Or read `agent.log` in `profiles/<profile>/logs/` if session DB is unavailable.
- Read FULL transcript (user messages + tool results + agent responses).

### Step 2 — Scan & classify (check ONE BY ONE)
For each item below, ask: PRESENT IN TRANSCRIPT? → if YES, add to list.

| # | Item | Folder (default profile) | Folder (profile X) | Format file |
|---|---|---|---|---|
| 1 | error/bug/mistake/traceback (real) | 01-AGENT-MEMORY/error-log/ | 01-AGENT-MEMORY/<X>/error-log/ | YYYY-MM-DD-[topic].md (Error/Root Cause/Fix/Prevention) |
| 2 | user correction of agent | 01-AGENT-MEMORY/corrections/ | 01-AGENT-MEMORY/<X>/corrections/ | YYYY-MM-DD-[topic].md |
| 3 | blocker agent cannot resolve alone | 01-AGENT-MEMORY/blockers/ | 01-AGENT-MEMORY/<X>/blockers/ | YYYY-MM-DD-[topic].md |
| 4 | design/architecture/config decision | 01-AGENT-MEMORY/decisions/ | 01-AGENT-MEMORY/<X>/decisions/ | YYYY-MM-DD-[topic].md |
| 5 | lesson learned | 01-AGENT-MEMORY/lessons-learned/ | 01-AGENT-MEMORY/<X>/lessons-learned/ | YYYY-MM-DD-[topic].md |
| 6 | recurring pattern / insight | 01-AGENT-MEMORY/patterns/ | 01-AGENT-MEMORY/<X>/patterns/ | YYYY-MM-DD-[topic].md |
| 7 | topic/tech not yet understood | 01-AGENT-MEMORY/knowledge-gaps/ | 01-AGENT-MEMORY/<X>/knowledge-gaps/ | YYYY-MM-DD-[topic].md |
| 8 | used a specific skill | 01-AGENT-MEMORY/skill-usage/ | 01-AGENT-MEMORY/<X>/skill-usage/ | YYYY-MM-DD-[topic].md (Skill/Task/Result) |
| 9 | entity/org/protocol (not person) | 02-KNOWLEDGE/entities/ | 02-KNOWLEDGE/entities/ (shared) | YYYY-MM-DD-[name].md |
| 10 | specific person | 02-KNOWLEDGE/people/ | 02-KNOWLEDGE/people/ (shared) | YYYY-MM-DD-[name].md |
| 11 | domain topic (ai/crypto/learning/new) | 02-KNOWLEDGE/topics/<domain>/ | 02-KNOWLEDGE/topics/<domain>/ (shared) | YYYY-MM-DD-[topic].md (link to concepts/entities, NOT duplicate) |
| 12 | project-related task | 05-PROJECT/active/<project>/LOG.md | same (shared) | append ## YYYY-MM-DD | [what done] |

**EXCLUSION (do NOT log as error):**
- cat/ls/grep/find returning nonzero DURING discovery (investigating) → not a bug.
- Error from a script THE AGENT ITSELF made for testing (intentional) → optional, unless there is a lesson.

### Step 3 — Write files
For each item in the list (Step 2):
1. `write_file(path, content)` — path relative to vault: `<VAULT_ROOT>/01-AGENT-MEMORY/...` (replace `<VAULT_ROOT>` with your vault path, e.g. `C:/Users/you/vault` or `~/vault`)
2. Frontmatter: `type`, `status: active`, `date: YYYY-MM-DD`, `tags: [...]`
3. Body: per the Format file column in the table.
4. `## Related` with at least 1 wikilink.
5. Auto-tag: `<HERMES_SCRIPTS>/auto-tag.py <file> --apply` (replace `<HERMES_SCRIPTS>` with your Hermes scripts path, e.g. `AppData/Local/hermes/scripts` on Windows or `~/.hermes/scripts` on Linux/Mac. Use `python` or `python3` per your env).

### Step 3b — Optional: script-assisted batch post-processing
If the companion vault-maintenance scripts are installed in `<HERMES_SCRIPTS>` (`auto-tag.py`, `wiki_connection_finder.py`, `moc_maintenance.py`, `realtime_log.py`), run the wrapper to automate tagging + connection-finding + MOC update + daily-note logging for all written files at once:
```bash
python3 <HERMES_SCRIPTS>/session_scan.py --files <file1,file2,...> --topic <topic> --type session-scan
```
This is the batch equivalent of Steps 3–4 above. It reads `VAULT_ROOT` and `HERMES_SCRIPTS` env vars (or edit the constants at the top of the script). Requires those 4 companion scripts present in `<HERMES_SCRIPTS>`; missing ones are skipped with a warning.

### Step 4 — Daily-note + Session-log (REQUIRED, use decision rule)
**Decision rule (distinguish the two):**
- Session scanned is just 1 simple task / a few short tasks → **daily-note only**.
- Session scanned is COMPLEX (hours of debugging / >10 tool calls / multi-step / user said "log session") → **BOTH**: session-log (narrative) + daily-note (1-line pointer).

**A. Daily-note (ALWAYS):** append 1 entry to `04-LOGS/daily-note/YYYY-MM-DD.md`:
- File does not exist today → `write_file` new.
- File already exists → `read_file` first, then `patch`/append NEW entry at the bottom. **Do NOT overwrite**, **Do NOT insert in the middle**.
- New entry timestamp must be ≥ last entry (chronological).

```markdown
## HH:MM | [scan] | Session scan — <N> items logged
**Items:** error-log:2, decisions:1, lessons:3, ...
**Files:** absolute paths
**Session-log:** (path if complex, or "-")
```

**B. Session-log (ONLY if complex):** write `04-LOGS/session-log/YYYY-MM-DD-[session-name].md`:
```markdown
# Session Log — [session name]
**Duration:** X tool calls / Y minutes
**Goal:** what was worked on
**Steps:** what was tried (step-by-step)
**Failed:** what failed (error/traceback)
**Resolution:** how it was resolved
**Lessons:** link to lessons-learned/ if any
```
Daily-note entry above points to this file.

### Step 5 — Report to user
```markdown
Session scan complete — <N> files written:
- error-log: 2 files (path...)
- decisions: 1 file (path...)
- ...
Topic seo has no folder → put in 00-NOTES/#needs-routing. Suggestion: create 02-KNOWLEDGE/topics/seo/
```
If a topic has no folder → MUST report suggestion to create the folder.

## PITFALLS
- Do NOT skip Step 2 classification → jumping straight to writing. Agent tends to log everything as noise.
- Do NOT duplicate: if a fact already exists in vault (check search_vault), update instead of creating new.
- Profile subfolder: ensure <X> is correct (coder/youtube/content), do not typo to root.
- Shared folders (02-KNOWLEDGE, 05-PROJECT) do NOT use profile subfolders.

## VERIFICATION
After writing, `ls` each target folder → confirm file exists. Report must show real paths, not "already logged".
