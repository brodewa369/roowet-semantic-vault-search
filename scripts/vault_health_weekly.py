#!/usr/bin/env python3
"""vault_health_weekly.py — Comprehensive vault health check.

Checks:
1. Orphan files (no inbound links)
2. Broken wikilinks (unresolvable)
3. Duplicate content (exact MD5)
4. Merge candidates (similar names/content)
5. Tag quality (missing, weird, inconsistent)
6. Index coverage (vault doctor)
7. Stale files (mtime)
8. File size distribution
9. Folder balance
"""

import os, re, json, hashlib, yaml, difflib
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter

VAULT_ROOT = Path(os.getenv("VAULT_ROOT", "./vault"))
REPORT_DIR = VAULT_ROOT / "04-LOGS" / "weekly-note"
SKIP_DIRS = {".obsidian", ".git", "__pycache__", "node_modules", ".trash", ".smart-env"}

# ─── Helpers ───────────────────────────────────────────────────────────

def safe_yaml(content):
    """Parse YAML frontmatter."""
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
    """Get all .md files in vault."""
    files = []
    for root, dirs, fnames in os.walk(VAULT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in fnames:
            if fn.endswith(".md"):
                files.append(Path(root) / fn)
    return files


def resolve_link(link, paths):
    """Resolve wikilink to file path (case-insensitive)."""
    l = link.split('|')[0].split('#')[0].strip().lower()
    if not l:
        return None
    
    # Build case-insensitive lookup
    ci = {rel.lower(): rel for rel in paths}
    
    # Exact match (with or without .md)
    if l in ci:
        return ci[l]
    if l + ".md" in ci:
        return ci[l + ".md"]
    
    # Basename match - extract stem from link and compare to file stem
    link_stem = Path(l).stem
    for rel, p in paths.items():
        if p.stem.lower() == link_stem:
            return rel
    
    # Path suffix match
    for rel in paths:
        if rel.lower().endswith("/" + l + ".md"):
            return rel
    
    return None


# ─── Check 1: Orphans ─────────────────────────────────────────────────

def check_orphans(files_dict):
    """Find files with no inbound links."""
    inbound = defaultdict(set)
    
    # Build path lookup
    paths = {rel: VAULT_ROOT / rel for rel in files_dict}
    
    for rel, content in files_dict.items():
        for m in re.finditer(r'\[\[([^\]]+)\]\]', content):
            link = m.group(1)
            target = resolve_link(link, paths)
            if target and target != rel:
                inbound[target].add(rel)
    
    orphans = []
    for rel in files_dict:
        if rel.endswith("index.md"):
            continue
        if rel in ("AGENTS.md", "SOUL.md"):
            continue
        if not inbound[rel]:
            orphans.append(rel)
    
    return sorted(orphans), dict(inbound)


# ─── Check 2: Broken Links ────────────────────────────────────────────

def check_broken_links(files_dict):
    """Find wikilinks that don't resolve.

    Skips: links inside code fences/inline code (examples, not links),
    and 06-SYSTEM/templates/ (placeholder links by design).
    """
    broken = []
    paths = {rel: VAULT_ROOT / rel for rel in files_dict}
    for rel, content in files_dict.items():
        if rel.startswith("06-SYSTEM/templates/"):
            continue
        # mask code so example links aren't counted
        def _blank(m):
            return re.sub(r"[^\n]", " ", m.group(0))
        content = re.sub(r"```.*?```", _blank, content, flags=re.S)
        content = re.sub(r"`[^`\n]+`", _blank, content)
        for m in re.finditer(r'\[\[([^\]]+)\]\]', content):
            link = m.group(1)
            target = resolve_link(link, paths)
            if not target:
                broken.append({"source": rel, "link": link})
    return broken


# ─── Check 3: Duplicates ──────────────────────────────────────────────

def check_duplicates(files_dict):
    """Find files with identical content."""
    hashes = defaultdict(list)
    for rel, content in files_dict.items():
        h = hashlib.md5(re.sub(r'\s+', '', content).encode()).hexdigest()
        hashes[h].append(rel)
    
    return {k: v for k, v in hashes.items() if len(v) > 1}


# ─── Check 4: Merge Candidates ────────────────────────────────────────

def check_merge_candidates(files_dict):
    """Find files that could be merged (similar names or content)."""
    candidates = []
    
    # Same stem, different folders
    by_stem = defaultdict(list)
    for rel in files_dict:
        by_stem[Path(rel).stem.lower()].append(rel)
    
    for stem, rels in by_stem.items():
        if len(rels) > 1 and stem not in ("index", "log", "overview", "readme"):
            # Same stem alone is not enough: a tool reference and its decision
            # record legitimately share a topic name (tools-routing pair is
            # ~0.06 similar). Require real content overlap to flag a merge.
            if len(rels) == 2:
                ratio = difflib.SequenceMatcher(
                    None, files_dict[rels[0]], files_dict[rels[1]]
                ).ratio()
                if ratio < 0.5:
                    continue
            candidates.append({"type": "same_name", "files": rels})
    
    # Similar content (first 200 chars)
    content_map = defaultdict(list)
    for rel, content in files_dict.items():
        preview = re.sub(r'\s+', '', content[:200])
        content_map[preview].append(rel)
    
    for preview, rels in content_map.items():
        if len(rels) > 1 and len(preview) > 50:
            # Merge candidates only apply to live files: archived snapshots
            # intentionally mirror their predecessors (frozen history,
            # cross-linked by design) - merging would destroy records.
            live = [r for r in rels if not r.startswith("05-PROJECT/archive/")]
            if len(live) < 2:
                continue
            candidates.append({"type": "similar_content", "files": live})
    
    return candidates


# ─── Check 5: Tag Quality ─────────────────────────────────────────────

def check_tags(files_dict):
    """Check tag quality across vault."""
    no_tags = []
    tag_counts = Counter()
    
    for rel, content in files_dict.items():
        if rel.endswith("index.md"):
            continue
        
        fm = safe_yaml(content)
        if not fm or "tags" not in fm:
            if len(content) > 300:
                no_tags.append(rel)
            continue
        
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        
        for tag in tags:
            tag_str = str(tag).strip().lower()
            if tag_str:
                tag_counts[tag_str] += 1
    
    # Find inconsistent tags (e.g., "active" vs "status/active")
    inconsistencies = []
    normalized = {}
    for tag in tag_counts:
        base = tag.split("/")[-1]
        if base == "research":
            continue  # dual-use sanctioned by agent-tagging-backlink-rules L27:
            # [research] = topic, [type/research] = research output
        if base in normalized and tag != normalized[base]:
            inconsistencies.append({
                "tag1": normalized[base],
                "tag2": tag,
                "count1": tag_counts[normalized[base]],
                "count2": tag_counts[tag],
            })
        else:
            normalized[base] = tag
    
    return {
        "no_tags": no_tags,
        "inconsistencies": sorted(inconsistencies, key=lambda x: -x["count1"]),
        "top_tags": tag_counts.most_common(20),
    }


# ─── Check 6: Index Coverage ──────────────────────────────────────────

def check_index_coverage():
    """Check LanceDB index coverage."""
    try:
        import lancedb
        db = lancedb.connect(os.path.expanduser("~/.hermes/vault_vectors"))
        table = db.open_table("vault_chunks")
        indexed = table.count_rows()
        
        # Count unique sources (scan rows directly - an empty FTS query
        # returns nothing, which wrongly reported 0 sources before)
        sources = set(table.to_arrow().column("source").to_pylist())
        
        return {
            "total_chunks": indexed,
            "unique_sources": len(sources),
            "status": "healthy" if indexed > 0 else "empty",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─── Check 7: Stale Files ─────────────────────────────────────────────

def check_stale_files(files_dict, days=90):
    """Find files not modified in N days."""
    stale = []
    cutoff = datetime.now() - timedelta(days=days)
    
    for rel, content in files_dict.items():
        try:
            p = VAULT_ROOT / rel
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            if mtime < cutoff:
                stale.append({
                    "file": rel,
                    "last_modified": mtime.strftime("%Y-%m-%d"),
                    "size_kb": p.stat().st_size // 1024,
                })
        except:
            pass
    
    return sorted(stale, key=lambda x: x["last_modified"])


# ─── Check 8: File Size Distribution ──────────────────────────────────

def check_file_sizes(files_dict):
    """Analyze file size distribution."""
    sizes = []
    for rel, content in files_dict.items():
        sizes.append((rel, len(content)))
    
    sizes.sort(key=lambda x: -x[1])
    
    # Find empty/tiny files
    empty = [r for r, s in sizes if s < 100]
    large = [r for r, s in sizes if s > 10000]
    
    return {
        "empty": empty,
        "large": large,
        "total_size_mb": sum(s for _, s in sizes) / 1024 / 1024,
        "avg_size_kb": sum(s for _, s in sizes) / max(len(sizes), 1) / 1024,
    }


# ─── Check 9: Folder Balance ──────────────────────────────────────────

def check_folder_balance(files_dict):
    """Analyze file distribution across folders."""
    folder_counts = Counter()
    for rel in files_dict:
        parts = rel.split("/")
        if len(parts) >= 2:
            folder_counts[parts[0] + "/" + parts[1]] += 1
        elif len(parts) == 1:
            folder_counts["(root)"] += 1
    
    return folder_counts.most_common()


# ─── Main ─────────────────────────────────────────────────────────────

def main():
    print("Vault Health Check — Comprehensive")
    print("=" * 60)
    
    # Load all files
    all_files = get_all_files()
    files_dict = {}
    for p in all_files:
        rel = str(p.relative_to(VAULT_ROOT))
        try:
            files_dict[rel] = p.read_text(encoding="utf-8", errors="replace")
        except:
            pass
    
    print(f"Total files: {len(files_dict)}")
    
    # Run checks
    print("\n[1/9] Checking orphans...")
    orphans, inbound = check_orphans(files_dict)
    
    print("[2/9] Checking broken links...")
    broken = check_broken_links(files_dict)
    
    print("[3/9] Checking duplicates...")
    dupes = check_duplicates(files_dict)
    
    print("[4/9] Checking merge candidates...")
    merge_cands = check_merge_candidates(files_dict)
    
    print("[5/9] Checking tag quality...")
    tag_report = check_tags(files_dict)
    
    print("[6/9] Checking index coverage...")
    index_report = check_index_coverage()
    
    print("[7/9] Checking stale files...")
    stale = check_stale_files(files_dict, 90)
    
    print("[8/9] Checking file sizes...")
    size_report = check_file_sizes(files_dict)
    
    print("[9/9] Checking folder balance...")
    folder_report = check_folder_balance(files_dict)
    
    # Generate report
    report = f"""---
type: report
status: active
date: {datetime.now().strftime('%Y-%m-%d')}
tags: [vault, health, report, weekly]
---

# Vault Health Report — {datetime.now().strftime('%Y-%m-%d')}

## Summary

| Metric | Count | Status |
|---|---|---|
| Total files | {len(files_dict)} | — |
| Orphans (no inbound) | {len(orphans)} | {'✅' if len(orphans) == 0 else '⚠️'} |
| Broken links | {len(broken)} | {'✅' if len(broken) == 0 else '⚠️'} |
| Exact duplicates | {len(dupes)} | {'✅' if len(dupes) == 0 else '⚠️'} |
| Merge candidates | {len(merge_cands)} | {'✅' if len(merge_cands) == 0 else 'ℹ️'} |
| Files without tags | {len(tag_report['no_tags'])} | {'✅' if len(tag_report['no_tags']) == 0 else '⚠️'} |
| Inconsistent tags | {len(tag_report['inconsistencies'])} | {'✅' if len(tag_report['inconsistencies']) == 0 else '⚠️'} |
| Stale files (90d) | {len(stale)} | {'✅' if len(stale) == 0 else 'ℹ️'} |
| Empty files | {len(size_report['empty'])} | {'✅' if len(size_report['empty']) == 0 else '⚠️'} |
| Index status | {index_report.get('status', 'unknown')} | {'✅' if index_report.get('status') == 'healthy' else '❌'} |

## Details

### 1. Orphans ({len(orphans)} files)
"""
    if orphans:
        for o in orphans[:30]:
            report += f"- {o}\n"
    else:
        report += "✅ No orphans found.\n"
    
    report += f"\n### 2. Broken Links ({len(broken)} links)\n"
    if broken:
        for b in broken[:30]:
            report += f"- `{b['source']}` → `[[{b['link']}]`\n"
    else:
        report += "✅ No broken links found.\n"
    
    report += f"\n### 3. Exact Duplicates ({len(dupes)} groups)\n"
    if dupes:
        for h, files in dupes.items():
            report += f"- {', '.join(files)}\n"
    else:
        report += "✅ No exact duplicates found.\n"
    
    report += f"\n### 4. Merge Candidates ({len(merge_cands)} groups)\n"
    if merge_cands:
        for mc in merge_cands[:20]:
            report += f"- [{mc['type']}] {', '.join(mc['files'])}\n"
    else:
        report += "✅ No merge candidates found.\n"
    
    report += f"\n### 5. Tag Quality\n"
    report += f"- Files without tags: {len(tag_report['no_tags'])}\n"
    report += f"- Inconsistent tags: {len(tag_report['inconsistencies'])}\n"
    
    if tag_report['no_tags']:
        report += "\n**Files without tags:**\n"
        for r in tag_report['no_tags'][:20]:
            report += f"- {r}\n"
    
    if tag_report['inconsistencies']:
        report += "\n**Inconsistent tags:**\n"
        for inc in tag_report['inconsistencies'][:10]:
            report += f"- `{inc['tag1']}` ({inc['count1']}x) vs `{inc['tag2']}` ({inc['count2']}x)\n"
    
    report += f"\n**Top 15 tags:**\n"
    for tag, count in tag_report['top_tags'][:15]:
        report += f"- `{tag}`: {count} files\n"
    
    report += f"\n### 6. Index Coverage\n"
    report += f"- Total chunks: {index_report.get('total_chunks', 'N/A')}\n"
    report += f"- Unique sources: {index_report.get('unique_sources', 'N/A')}\n"
    report += f"- Status: {index_report.get('status', 'N/A')}\n"
    
    report += f"\n### 7. Stale Files ({len(stale)} files, 90+ days)\n"
    if stale:
        for s in stale[:20]:
            report += f"- `{s['file']}` (modified: {s['last_modified']}, {s['size_kb']}KB)\n"
    else:
        report += "✅ No stale files.\n"
    
    report += f"\n### 8. File Sizes\n"
    report += f"- Total size: {size_report['total_size_mb']:.1f} MB\n"
    report += f"- Average size: {size_report['avg_size_kb']:.1f} KB\n"
    report += f"- Empty files (<100B): {len(size_report['empty'])}\n"
    report += f"- Large files (>10KB): {len(size_report['large'])}\n"
    
    if size_report['empty']:
        report += "\n**Empty files:**\n"
        for r in size_report['empty'][:15]:
            report += f"- {r}\n"
    
    report += f"\n### 9. Folder Balance\n"
    for folder, count in folder_report:
        report += f"- `{folder}`: {count} files\n"
    
    report += f"\n---\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
    
    # Save report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{datetime.now().strftime('%Y-%m-%d')}-vault-health.md"
    report_path.write_text(report, encoding="utf-8")
    
    print(f"\n✅ Report saved: {report_path}")
    print(f"\nSummary: {len(orphans)} orphans, {len(broken)} broken, {len(dupes)} dupes, {len(merge_cands)} merge, {len(tag_report['no_tags'])} no-tags")


if __name__ == "__main__":
    main()
