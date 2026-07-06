# Agent Writing Rules — Cara Agent Mengisi Vault

> Setiap kali agent selesai task, WAJIB capture output ke vault.
> Ini yang membedakan vault yang hidup vs vault yang mati.

---

## Golden Rule

**Setiap task selesai → minimal tulis daily note.**
Kalau task menghasilkan knowledge/error/keputusan → tulis juga ke folder yang sesuai.

## Mapping: Output → Folder

| Situasi | Folder | Template | Wajib? |
|---------|--------|----------|--------|
| Task selesai (apapun) | `04-LOGS/daily-note/` | `template-daily.md` | ✅ WAJIB |
| Ketemu error / bug | `01-AGENT-MEMORY/error-log/` | `template-error.md` | ✅ WAJIB |
| Bikin keputusan | `01-AGENT-MEMORY/decisions/` | `template-decision.md` | ✅ WAJIB |
| Dapet koreksi dari user | `01-AGENT-MEMORY/corrections/` | — | ✅ WAJIB |
| Belajar konsep baru | `02-KNOWLEDGE/concepts/` | `template-concept.md` | 👍 Recommended |
| Ketemu orang/entitas baru | `02-KNOWLEDGE/entities/` | `template-entity.md` | 👍 Recommended |
| Dapet insight/pattern | `01-AGENT-MEMORY/patterns/` | `template-pattern.md` | 🔧 Kalau penting |
| Dapet resource bagus | `02-KNOWLEDGE/resources/` | — | 🔧 Kalau berguna |
| Research selesai | `03-RESEARCH/analyses/` | `template-analysis.md` | 🔧 Untuk research task |
| Project update | `05-PROJECTS/active/` | `template-project.md` | 🔧 Untuk project task |
| Skill usage | `01-AGENT-MEMORY/skill-usage/` | — | 🔧 Internal tracking |

## Step-by-Step

### 1. Selesai Task → Daily Note DULU

```markdown
## HH:MM | [task-type] | [judul singkat]
**Perintah:** [apa yang user minta]
**Yang dikerjakan:** [detail]
**Hasil:** [output/kesimpulan]
**Files created:** [list files]
**Error/catatan:** [kalau ada]
---
```

### 2. Cek Apakah Ada Output Lain

Jalanin checklist ini SETIAP task selesai, SEBELUM bilang "done":

```
[ ] Error/bug terjadi? → tulis ke error-log/
[ ] Keputusan dibuat? → tulis ke decisions/
[ ] User ngasih koreksi? → tulis ke corrections/
[ ] Konsep baru dipelajari? → tulis ke concepts/
[ ] Pattern baru? → tulis ke patterns/
[ ] Insight penting? → tulis ke lessons-learned/
```

### 3. Tulis File

- Pakai template yang sesuai dari `06-SYSTEM/templates/`
- Tambah frontmatter: `type`, `status`, `date`, `tags`
- Format nama: `YYYY-MM-DD-topic-name.md`
- Tambah `## Related` dengan 1-2 wikilink
- Satu file = satu topik. Jangan campur.

### 4. Final Check

- ✅ File udah ada di folder yang bener?
- ✅ Pakai template yang sesuai?
- ✅ Ada frontmatter?
- ✅ Ada Related section?
- ✅ Nama file sesuai konvensi?

## Rules Summary

1. **Daily note AFTER every task.** No exceptions.
2. **Agent NEVER creates folders.** If no folder fits → `00-NOTES/` with `#needs-routing`.
3. **One topic per file.** Never combine.
4. **Never overwrite.** Use `-v2` suffix.
5. **Never delete** without explicit user confirmation.
6. **Templates** are in `06-SYSTEM/templates/` — read before writing.
