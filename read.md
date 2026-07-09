# Read Me — Setup & Skills

Panduan singkat buat pakai repo ini. Baca sebelum jalanin biar agent gak bingung soal path.

---

## ⚠️ WAJIB: Ganti Path Sebelum Pakai

File di repo ini pakai **placeholder generic**, BUKAN path PC tertentu. Ganti sebelum dijalankan:

| Placeholder | Artinya | Contoh (Windows) | Contoh (Linux/Mac) |
|---|---|---|---|
| `<VAULT_ROOT>` | Path ke vault markdown lo | `C:/Users/you/vault` | `~/vault` |
| `<HERMES_SCRIPTS>` | Path ke folder script Hermes | `AppData/Local/hermes/scripts` | `~/.hermes/scripts` |

**Di `skills/skill/scanthissession/SKILL.md`:**
- `<VAULT_ROOT>/01-AGENT-MEMORY/...` → ganti `<VAULT_ROOT>` jadi path vault lo
- `<HERMES_SCRIPTS>/auto-tag.py` → ganti `<HERMES_SCRIPTS>` jadi path script Hermes lo

**Kenapa?** Repo ini public — gak boleh hardcode path PC orang lain. Kalau placeholder gak diganti, agent tulis ke path yang gak ada → error / file hilang.

**SOUL.md / CLAUDE.md:** Template generic (gak ada hardcoded path). Yang perlu di-set user: `VAULT_ROOT` di `.env` (lihat `AGENTS.md` → Technical MCP Context) biar `search_vault()` jalan.

**Fungsi beda (penting):**
- `SOUL.md` → untuk agent di LUAR Claude Code (Hermes, Codex, OpenClaw, OpenCode, dll)
- `CLAUDE.md` → untuk Claude / Claude Code / Claude Desktop
- Isi keduanya SAMA (agent-identity template), cuma fungsi beda.

---

## Cara Pakai Skill: `/scanthissession`

**Fungsi singkat:**
Agent scan session transcript (percakapan sekarang), deteksi item vault (error, keputusan, koreksi, lesson, dll), lalu **TULIS otomatis ke folder vault yang benar** sesuai aturan. Ini solusi biar agent gak "lupa" log — skill MEMAKSA scan + write, bukan cuma instruction pasif.

**Command:**
```
/scanthissession
```
Atau bilang ke agent: `"scan session"`, `"log session ini"`.

**Kapan pakai:**
- Selesai kerja session panjang (>10 tool calls)
- Sebelum tutup session
- Pas mau pastiin semua error/decision/lesson ke-catat ke vault

**Output:** File ditulis ke `<VAULT_ROOT>/01-AGENT-MEMORY/...` + daily-note di-update. Agent lapor path file yang dibuat.

---

## Struktur Skills
```
skills/
├── skill/                  # folder pembungkus
│   └── scanthissession/    # skill session scanner
│       └── SKILL.md
└── (read.md ini ada di root repo, bukan di sini)
```
