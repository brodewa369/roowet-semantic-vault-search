# Obsidian Setup — Recommended Plugins and Config

> Agar vault bisa dimanage dengan baik dan agent bisa bantu buat MOC, routing, dan lain-lain.

## Core Plugins (enable these)

| Plugin | Fungsi |
|--------|--------|
| File Explorer | Navigasi folder |
| Graph | Lihat koneksi antar notes |
| Backlink | Lihat siapa yang link ke note ini |
| Outgoing Link | Lihat link dari note ini |
| Tag Pane | Navigasi via tags |
| Daily Notes | Auto-create daily notes |
| Templates | Load template pas bikin note baru |
| Command Palette | Cepet akses command |
| Outline | Table of contents per note |
| Properties | YAML frontmatter editor |
| Canvas | Visual mind mapping |
| Bookmark | Save sering diakses |

## Community Plugins (recommended)

| Plugin | Fungsi | Wajib? |
|--------|--------|--------|
| **Templater** | Advanced templates (variable, date, file info) | Wajib |
| **Calendar** | Kalender sidebar, klik tanggal buat daily note | Recommended |
| **Dataview** | Query notes kayak database (by tag, folder, frontmatter) | Recommended |
| **Excalidraw** | Drawing and diagram dalam vault | Recommended |
| **Obsidian Note Linker** | Auto-suggest link ke notes yang related | Opsional |
| **Smart Connections** | AI-based note connections (local) | Opsional |

## Cara Install

```
Settings > Community plugins > Browse >
Cari plugin > Install > Enable
```

## Templater Setup

Biar template di `06-SYSTEM/templates/` bisa dipake:

1. Install Templater
2. Settings > Templater > Template folder location:
   `06-SYSTEM/templates/`
3. Pas bikin note baru:
   - `Ctrl/Cmd + P` > `Templater: Insert template`
   - Pilih template sesuai jenis content

## Theme

Default Obsidian theme works fine. Recommended: **Minimal** (clean, supports all plugins).

## Vault Location

Simpan vault di folder yang sama dengan `VAULT_ROOT` di `.env`:

```env
VAULT_ROOT=C:/Users/you/path/to/vault
```
