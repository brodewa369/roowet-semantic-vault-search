---
name: scanthissession
description: Scan current or active session transcript, detect vault-relevant items (topic, blocker, correction, decision, error/bug, knowledge-gap, lesson, pattern, skill-usage, entity, person, topic), then WRITE them to the correct vault folder per rules. Use after a work session, when user says scan session, or before ending a long task. Trigger words scan session, log session ini, scanthisession.
---

# /scanthissession — Session Scanner & Vault Writer

## PURPOSE
LLM tidak otomatis log error/fact pas ketemu (instruction pasif gagal). Skill ini MEMAKSA scan + write lewat procedure eksplisit. Agent jalanin skill ini → dia WAJIB baca session, klasifikasi, dan tulis file.

## WHEN TO RUN
- User: scan session, scan this session, log session ini, /scanthissession
- Atau agent selesai task kompleks (>10 tool calls) → run sebagai cleanup
- JANGAN run pas user lagi mid-task (kecuali dia suruh)

## PROCEDURE (jalankan step by step)

### Step 1 — Ambil session transcript
- Default profile: `hermes sessions list` → cari session aktif → baca lewat `session_search(session_id=...)`.
- Profile lain: `hermes -p <profile> sessions list` lalu `session_search`.
- Atau baca `agent.log` di `profiles/<profile>/logs/` kalau session DB gak ada.
- Baca FULL transcript (user messages + tool results + agent responses).

### Step 2 — Scan & klasifikasi (cek SATU-SATU)
Untuk tiap item di bawah, tanya: ADA DI TRANSCRIPT? → kalau YA, catat ke list.

| # | Item | Folder (default profile) | Folder (profile X) | Format file |
|---|---|---|---|---|
| 1 | error/bug/mistake/traceback NYATA | 01-AGENT-MEMORY/error-log/ | 01-AGENT-MEMORY/<X>/error-log/ | YYYY-MM-DD-[topic].md (Error/Root Cause/Fix/Prevention) |
| 2 | user koreksi agent | 01-AGENT-MEMORY/corrections/ | 01-AGENT-MEMORY/<X>/corrections/ | YYYY-MM-DD-[topic].md |
| 3 | halangan gak bisa selesaikan sendiri | 01-AGENT-MEMORY/blockers/ | 01-AGENT-MEMORY/<X>/blockers/ | YYYY-MM-DD-[topic].md |
| 4 | keputusan desain/arsitektur/konfig | 01-AGENT-MEMORY/decisions/ | 01-AGENT-MEMORY/<X>/decisions/ | YYYY-MM-DD-[topic].md |
| 5 | lesson learned | 01-AGENT-MEMORY/lessons-learned/ | 01-AGENT-MEMORY/<X>/lessons-learned/ | YYYY-MM-DD-[topic].md |
| 6 | recurring pattern / insight | 01-AGENT-MEMORY/patterns/ | 01-AGENT-MEMORY/<X>/patterns/ | YYYY-MM-DD-[topic].md |
| 7 | topik/teknologi belum paham | 01-AGENT-MEMORY/knowledge-gaps/ | 01-AGENT-MEMORY/<X>/knowledge-gaps/ | YYYY-MM-DD-[topic].md |
| 8 | pakai skill tertentu | 01-AGENT-MEMORY/skill-usage/ | 01-AGENT-MEMORY/<X>/skill-usage/ | YYYY-MM-DD-[topic].md (Skill/Task/Result) |
| 9 | entitas/org/protokol (bukan orang) | 02-KNOWLEDGE/entities/ | 02-KNOWLEDGE/entities/ (shared) | YYYY-MM-DD-[name].md |
| 10 | orang spesifik | 02-KNOWLEDGE/people/ | 02-KNOWLEDGE/people/ (shared) | YYYY-MM-DD-[name].md |
| 11 | topik domain (ai/crypto/learning/baru) | 02-KNOWLEDGE/topics/<domain>/ | 02-KNOWLEDGE/topics/<domain>/ (shared) | YYYY-MM-DD-[topic].md (link ke concepts/entities, BUKAN duplicate) |
| 12 | task berkaitan project | 05-PROJECT/active/<project>/LOG.md | same (shared) | append ## YYYY-MM-DD | [what done] |

**EXCLUSION (jangan log sebagai error):**
- cat/ls/grep/find return nonzero SAAT discovery (cari tau) → itu bukan bug.
- Error dari script YANG AGENT SENDIRI BUAT buat test (intentional) → gak wajib, kecuali ada lesson darinya.

### Step 3 — Write files
Untuk tiap item di list (Step 2):
1. `write_file(path, content)` — path absolut `C:/Users/GGID/wiki/...`
2. Frontmatter: `type`, `status: active`, `date: YYYY-MM-DD`, `tags: [...]`
3. Body: sesuai format kolom Format file di tabel.
4. `## Related` minimal 1 wikilink.
5. Auto-tag: `python3 AppData/Local/hermes/scripts/auto-tag.py <file> --apply` (ada di Windows? pakai `python` kalau `python3` gak ada).

### Step 4 — Daily-note + Session-log (WAJIB, pakai decision rule)
**Decision rule (bedain keduanya):**
- Session yang di-scan CUKUP 1 task simpel / beberapa task pendek → **daily-note aja**.
- Session yang di-scan KOMPLEKS (debugging berjam-jam / >10 tool calls / multi-step / user bilang "log session") → **BOTH**: session-log (narrative) + daily-note (1 line pointer).

**A. Daily-note (SELALU):** append 1 entry ke `04-LOGS/daily-note/YYYY-MM-DD.md`:
- File belum ada hari ini → `write_file` baru.
- File SUDAH ada → `read_file` dulu, lalu `patch`/append entry BARU di paling bawah. **JANGAN overwrite**, **JANGAN insert di tengah**.
- Timestamp entry baru harus ≥ entry terakhir (urut waktu).
```
## HH:MM | [scan] | Session scan — <N> items logged
**Items:** error-log:2, decisions:1, lessons:3, ...
**Files:** list absolut
**Session-log:** (isi path kalau session kompleks, atau "-")
```

**B. Session-log (HANYA kalau kompleks):** tulis `04-LOGS/session-log/YYYY-MM-DD-[nama-session].md`:
```
# Session Log — [nama session]
**Durasi:** X tool calls / Y menit
**Goal:** apa yang dikerjakan
**Steps:** apa yang dicoba (step-by-step)
**Failed:** apa yang gagal (error/traceback)
**Resolution:** gimana nyelesain
**Lessons:** link ke lessons-learned/ kalau ada
```
Daily-note entry di atas pointer ke file ini.

### Step 5 — Report ke user
```
Session scan selesai — <N> file ditulis:
- error-log: 2 file (path...)
- decisions: 1 file (path...)
- ...
Topic seo gak ada folder → taruh di 00-NOTES/#needs-routing. Saran: buat 02-KNOWLEDGE/topics/seo/
```
Kalau ada topic gak ada folder → WAJIB lapor saran bikin folder.

## PITFALLS
- JANGAN skip Step 2 klasifikasi → langsung nulis. Agent suka log semua jadi noise.
- JANGAN duplicate: kalau fact udah ada di vault (cek search_vault), update bukan buat baru.
- Profile subfolder: pastikan <X> benar (coder/youtube/content), jangan typo ke root.
- Shared folders (02-KNOWLEDGE, 05-PROJECT) TIDAK pakai subfolder profile.

## VERIFICATION
Setelah write, `ls` tiap folder target → confirm file ada. Report harus ada path nyata, bukan sudah di-log.
