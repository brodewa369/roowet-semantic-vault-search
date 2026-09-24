#!/usr/bin/env python3
"""Auto-generate index.md files for all vault folders (recursive)."""

import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")  # repo root (setup.sh)
from datetime import datetime

VAULT_ROOT = os.getenv("VAULT_ROOT", "./vault")
EXCLUDE_DIRS = {".obsidian", ".git", "__pycache__", "06-SYSTEM/templates"}
MIN_FILES_FOR_INDEX = 3


def read_frontmatter(content: str) -> dict:
    fm = {}
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    fm[k.strip()] = v.strip().strip("[]\"' ")
    return fm


def get_title_from_content(content: str, filepath: str) -> str:
    fm = read_frontmatter(content)
    if fm.get("title"):
        return fm["title"]
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return Path(filepath).stem


def generate_index_for_folder(folder_path: str, vault_root: str) -> str:
    folder_name = Path(folder_path).name
    rel_path = Path(folder_path).relative_to(vault_root)
    
    md_files = sorted([
        f for f in Path(folder_path).glob("*.md")
        if f.is_file() and f.name != "index.md"
    ])
    
    if len(md_files) < MIN_FILES_FOR_INDEX:
        return ""
    
    file_entries = []
    for f in md_files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            title = get_title_from_content(content, str(f))
            fm = read_frontmatter(content)
            desc = fm.get("description", "")
            status = fm.get("status", "")
            
            if not desc:
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("---") and not line.startswith("[["):
                        desc = line[:120]
                        break
            
            file_entries.append({
                "file": f,
                "title": title,
                "description": desc,
                "status": status,
                "path": str(f.relative_to(vault_root)),
            })
        except Exception:
            pass
    
    active = [e for e in file_entries if e.get("status") == "active"]
    
    lines = [
        "---",
        "type: index",
        "auto-generated: true",
        f"folder: {rel_path}",
        f"generated_at: {datetime.now().strftime('%Y-%m-%d')}",
        f"file_count: {len(file_entries)}",
        "---",
        "",
        f"# {folder_name} — Index",
        "",
        f"*{rel_path}* — {len(file_entries)} files",
        "",
    ]
    
    if active:
        lines.append("## Active")
        lines.append("")
        for e in active:
            desc = e["description"][:80] if e["description"] else ""
            lines.append(f"- [[{e['file'].stem}]]" + (f" — {desc}" if desc else ""))
        lines.append("")
    
    lines.append("## All Files")
    lines.append("")
    for e in file_entries:
        desc = e["description"][:80] if e["description"] else ""
        status_tag = f" `{e['status']}`" if e["status"] else ""
        lines.append(f"- [[{e['file'].stem}]]" + (f" — {desc}" if desc else "") + status_tag)
    
    lines.append("")
    
    related = set()
    for e in file_entries:
        try:
            content = e["file"].read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r'\[\[([^\]|#]+)', content):
                link = match.group(1).strip()
                potential = vault_root / link / "index.md"
                if potential.exists() and str(potential) != str(Path(folder_path) / "index.md"):
                    related.add(link)
        except Exception:
            pass
    
    if related:
        lines.append("## Related Folders")
        lines.append("")
        for r in sorted(related):
            lines.append(f"- [[{r}]]")
        lines.append("")
    
    return "\n".join(lines)


def main():
    vault = Path(VAULT_ROOT)
    generated = []
    skipped = []
    
    # Walk all directories recursively
    for root, dirs, files in os.walk(vault):
        # Skip excluded dirs
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith(".")]
        
        folder = Path(root)
        index_path = folder / "index.md"
        
        # Skip if manual
        if index_path.exists():
            try:
                existing = index_path.read_text(encoding="utf-8", errors="replace")
                if "auto-generated: true" not in existing:
                    skipped.append(str(folder.relative_to(VAULT_ROOT)))
                    continue
            except Exception:
                pass
        
        content = generate_index_for_folder(str(folder), VAULT_ROOT)
        if content:
            index_path.write_text(content, encoding="utf-8")
            generated.append(str(folder.relative_to(VAULT_ROOT)))
    
    print(f"Generated: {len(generated)} folders")
    for g in generated:
        print(f"  ✓ {g}/index.md")
    print(f"Skipped (manual): {len(skipped)} folders")
    for s in skipped:
        print(f"  - {s}")


if __name__ == "__main__":
    main()
