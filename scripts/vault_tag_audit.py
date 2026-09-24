#!/usr/bin/env python3
"""vault_tag_audit.py — Detect tag quality issues and suggest fixes.

Checks:
1. Single-use tags (should be merged)
2. Tag inconsistencies (prefixed vs unprefixed)
3. Orphan files (no inbound links)
4. Files without ## Related section
5. Files with empty ## Related section
6. Tag explosion (too many unique tags)

Usage:
    python scripts/vault_tag_audit.py          # Report only
    python scripts/vault_tag_audit.py --fix    # Auto-fix what's safe
"""

import os
import re
import yaml
import hashlib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")  # repo root (setup.sh)
from collections import Counter, defaultdict
from datetime import datetime

VAULT_ROOT = Path(os.getenv("VAULT_ROOT", "./vault"))
REPORT_DIR = VAULT_ROOT / "04-LOGS" / "weekly-note"
SKIP_DIRS = {".obsidian", ".git", "__pycache__", "node_modules", ".trash", ".smart-env"}

def safe_yaml(content):
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
        return fm if isinstance(fm, dict) else None
    except:
        return None

def get_all_files():
    files = []
    for root, dirs, fnames in os.walk(VAULT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in fnames:
            if fn.endswith(".md"):
                files.append(Path(root) / fn)
    return files

def resolve_link(link, paths):
    l = link.split("|")[0].split("#")[0].strip().lower()
    if not l:
        return None
    ci = {rel.lower(): rel for rel in paths}
    if l in ci:
        return ci[l]
    if l + ".md" in ci:
        return ci[l + ".md"]
    link_stem = Path(l).stem
    for rel, p in paths.items():
        if p.stem.lower() == link_stem:
            return rel
    for rel in paths:
        if rel.lower().endswith("/" + l + ".md"):
            return rel
    return None

def main():
    auto_fix = "--fix" in os.sys.argv
    files = get_all_files()
    
    # Collect data
    all_tags = Counter()
    tag_files = defaultdict(list)
    files_without_tags = []
    inbound_links = defaultdict(list)
    outbound_links = defaultdict(list)
    files_without_related = []
    files_empty_related = []
    files_without_outbound = []
    
    # Build path lookup
    paths = {}
    for p in files:
        rel = str(p.relative_to(VAULT_ROOT))
        paths[rel] = p
    
    for p in files:
        rel = str(p.relative_to(VAULT_ROOT))
        try:
            text = p.read_text(encoding="utf-8")
            fm = safe_yaml(text)
            
            # Tags
            if fm and "tags" in fm:
                tags = fm.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",")]
                for t in tags:
                    t_str = str(t).lower().strip()
                    all_tags[t_str] += 1
                    tag_files[t_str].append(rel)
            else:
                files_without_tags.append(rel)
            
            # Backlinks
            if "## Related" in text:
                related_section = text.split("## Related", 1)[1]
                if "[[" in related_section:
                    for m in re.finditer(r'\[\[([^\]|#]+)', related_section):
                        target = m.group(1).strip()
                        resolved = resolve_link(target, paths)
                        if resolved and resolved != rel:
                            outbound_links[rel].append(resolved)
                            inbound_links[resolved].append(rel)
                else:
                    files_empty_related.append(rel)
            else:
                files_without_related.append(rel)
            
            # Outbound links
            for m in re.finditer(r'\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]', text):
                target = m.group(1).strip()
                resolved = resolve_link(target, paths)
                if resolved and resolved != rel:
                    outbound_links[rel].append(resolved)
                    inbound_links[resolved].append(rel)
        except:
            pass
    
    # Find orphans
    orphans = [f for f in paths if f not in inbound_links]
    
    # Find single-use tags
    single_use = {t: f for t, f in tag_files.items() if len(f) == 1}
    
    # Find tag inconsistencies
    base_names = defaultdict(list)
    for tag in all_tags:
        base = tag.split("/")[-1] if "/" in tag else tag
        base_names[base].append(tag)
    
    inconsistencies = {b: tags for b, tags in base_names.items() if len(tags) > 1}
    
    # Generate report
    report = []
    report.append(f"# Vault Tag Audit Report — {datetime.now().strftime('%Y-%m-%d')}")
    report.append("")
    report.append(f"Total files: {len(files)}")
    report.append(f"Unique tags: {len(all_tags)}")
    report.append(f"Files without tags: {len(files_without_tags)}")
    report.append(f"Orphan files (no inbound links): {len(orphans)}")
    report.append(f"Files without ## Related: {len(files_without_related)}")
    report.append(f"Files with empty ## Related: {len(files_empty_related)}")
    report.append(f"Single-use tags: {len(single_use)}")
    report.append(f"Tag inconsistencies: {len(inconsistencies)}")
    report.append("")
    
    # Single-use tags
    report.append("## Single-Use Tags (merge recommended)")
    report.append("")
    for tag, files in sorted(single_use.items(), key=lambda x: x[0])[:30]:
        report.append(f"- `{tag}` → {files[0]}")
    if len(single_use) > 30:
        report.append(f"- ... and {len(single_use) - 30} more")
    report.append("")
    
    # Inconsistencies
    report.append("## Tag Inconsistencies (standardize)")
    report.append("")
    for base, tags in sorted(inconsistencies.items()):
        total = sum(all_tags[t] for t in tags)
        if total > 2:
            report.append(f"### {base} ({total} files)")
            for t in sorted(tags, key=lambda x: -all_tags[x]):
                report.append(f"- `{t}`: {all_tags[t]} files")
            report.append("")
    
    # Orphans
    report.append("## Orphan Files (no inbound links)")
    report.append("")
    for f in sorted(orphans)[:20]:
        report.append(f"- {f}")
    if len(orphans) > 20:
        report.append(f"- ... and {len(orphans) - 20} more")
    report.append("")
    
    # Files without related
    report.append("## Files Without ## Related Section")
    report.append("")
    for f in sorted(files_without_related)[:20]:
        report.append(f"- {f}")
    if len(files_without_related) > 20:
        report.append(f"- ... and {len(files_without_related) - 20} more")
    report.append("")
    
    # Write report
    report_text = "\n".join(report)
    print(report_text)
    
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{datetime.now().strftime('%Y-%m-%d')}-tag-audit.md"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"\nReport saved to: {report_path}")

if __name__ == "__main__":
    main()
