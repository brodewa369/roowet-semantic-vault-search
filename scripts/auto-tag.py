#!/usr/bin/env python3
"""
auto-tag.py — Auto-tagging system for Obsidian vault files (v2).
Extracts tags from content using 4 categories: topic, status, type, project.
Implements full decision tree from auto-tagging-system-v2 concept.

Usage:
    python3 auto-tag.py <file_path>           # Preview tags (JSON)
    python3 auto-tag.py <file_path> --apply   # Write tags to file frontmatter
    python3 auto-tag.py <file_path> --check   # Check tag consistency

Output: JSON with suggested tags
"""

import os
import sys
import re
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load .env: script dir (CLI convention) then repo root (setup.sh creates it there)
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

WIKI_ROOT = Path(os.getenv("VAULT_ROOT", "./vault"))

# ═══════════════════════════════════════════════════════════════════════════════
# 1. TOPIC KEYWORDS (keyword → tag)
# ═══════════════════════════════════════════════════════════════════════════════

TOPIC_KEYWORDS = {
    # ── Crypto / Blockchain ──────────────────────────────────────────────────
    "crypto": "crypto", "cryptocurrency": "crypto", "bitcoin": "btc",
    "ethereum": "ethereum", "solana": "solana", "defi": "defi",
    "pump.fun": "pump-fun", "pump fun": "pump-fun",
    "wallet": "wallet", "trading": "trading", "token": "token",
    "blockchain": "blockchain", "nft": "nft", "yield": "yield-farming",
    "liquidity": "liquidity", "amm": "amm", "dex": "dex",
    "bridge": "bridge", "rollup": "rollup", "zk": "zk-proofs",
    "zero-knowledge": "zk-proofs", "zkp": "zk-proofs",
    "smart contract": "smart-contract", "consensus": "consensus",
    "layer-2": "layer-2", "l2": "layer-2", "scalability": "scaling",
    "merkle": "merkle-tree", "hash": "hashing", "signature": "cryptography",
    "stop-loss": "risk-management", "risk": "risk-management",
    "portfolio": "portfolio", "leverage": "leverage", "margin": "margin",
    # ── AI / ML ───────────────────────────────────────────────────────────────
    "ai": "ai", "artificial intelligence": "ai", "llm": "llm",
    "machine learning": "machine-learning", "deep learning": "deep-learning",
    "agent": "agent", "claude": "claude", "gpt": "gpt",
    "hermes": "hermes", "mcp": "mcp", "model": "model",
    "neural": "neural-network", "transformer": "transformer",
    "prompt": "prompt-engineering", "fine-tuning": "fine-tuning",
    "rag": "rag", "embedding": "embedding", "vector": "vector-db",
    "inference": "inference", "training": "training", "dataset": "dataset",
    "automation": "automation", "bot": "bot", "workflow": "workflow",
    # ── Obsidian / Knowledge Management ───────────────────────────────────────
    "obsidian": "obsidian", "vault": "vault", "note": "note-taking",
    "knowledge": "knowledge-management", "second brain": "second-brain",
    "moc": "moc", "zettelkasten": "zettelkasten",
    "template": "template", "frontmatter": "frontmatter",
    "backlink": "backlink", "wikilink": "wikilink", "graph": "graph-view",
    "connection": "connection", "link": "link", "tag": "tagging",
    "index": "index", "navigation": "navigation",
    # ── Hermes / Tools / Infra ────────────────────────────────────────────────
    "hermes agent": "hermes", "cron": "cron", "skill": "skill",
    "puppeteer": "puppeteer", "browser": "browser-automation",
    "scraper": "scraper", "api": "api", "script": "script",
    "ollama": "ollama", "lancedb": "lancedb", "semantic": "semantic-search",
    "docker": "docker", "git": "git", "github": "github",
    "windows": "windows", "telegram": "telegram", "cli": "cli",
    # ── Security ──────────────────────────────────────────────────────────────
    "exploit": "security", "vulnerability": "security",
    "rug pull": "security", "sandwich attack": "security",
    "audit": "audit", "honeypot": "honeypot", "firewall": "firewall",
    "encryption": "encryption", "auth": "authentication",
    # ── Trading / Finance ─────────────────────────────────────────────────────
    "scalping": "scalping", "arbitrage": "arbitrage", "yield": "yield-farming",
    "staking": "staking", "farming": "yield-farming", "airdrop": "airdrop",
    "pnl": "pnl", "roi": "roi", "apy": "apy", "tvl": "tvl",
    # ── Learning ──────────────────────────────────────────────────────────────
    "tutorial": "tutorial", "course": "course", "guide": "guide",
    "documentation": "documentation", "reference": "reference",
    "research": "research", "analysis": "analysis", "review": "review",
}

# ═══════════════════════════════════════════════════════════════════════════════
# 2. PROJECT INDICATORS (keyword → project tag)
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_INDICATORS = {
    "ggscalping": "project/ggscalping",
    "gg scalping": "project/ggscalping",
    "gmgn": "project/gmgn",
    "research pipeline": "project/research-pipeline",
    "obsidian brain": "project/obsidian-brain",
    "deep research": "project/research-pipeline",
    "vault restructure": "project/obsidian-brain",
    "auto-tag": "project/obsidian-brain",
    "connection finder": "project/obsidian-brain",
}

# ═══════════════════════════════════════════════════════════════════════════════
# 3. TYPE INDICATORS (content pattern → type tag)
# ═══════════════════════════════════════════════════════════════════════════════

TYPE_INDICATORS = [
    # Order matters — first match wins
    (r"(error|bug|crash|failed|traceback|exception|stack trace)", "error"),
    (r"(mistake|salahan|lesson learned|what went wrong|wrong)", "mistake"),
    (r"(decide|chose|keputusan|decided|pilih|selected|opted)", "decision"),
    (r"(concept|definition|definisi|teori|what is|apa itu|introduction)", "concept"),
    (r"(analysis|analisis|deep dive|investigate|examination|breakdown)", "analysis"),
    (r"(compare|vs|versus|perbandingan|comparison|differences? between)", "comparison"),
    (r"(raw|source|original|immutable|capture|uncropped)", "raw"),
    (r"(synthesis|sintesis|central claim|overall|cross.note|cross-topic)", "synthesis"),
    (r"(pattern|pola|recurring|repeated|consistent across)", "pattern"),
    (r"(map of content|moc|navigation hub|topic map|index page)", "moc"),
    (r"(connection report|strong connection|weak connection|missing link)", "connection-report"),
    (r"(entity|person|profile|orang|company|project profile)", "entity"),
    (r"(fact|fakta|statistic|data point|standalone fact)", "fact"),
    (r"(resource|referensi|bookmark|reading list|collection)", "resource"),
    (r"(tool|mcp|script|utility|automation tool)", "tool"),
    (r"(prompt|template prompt|ai prompt|system prompt)", "prompt"),
    (r"(daily.note|daily log|today|morning brief|evening reflection)", "daily"),
    (r"(session.log|session capture|session summary|scan session)", "session"),
    (r"(trading|trade|position|entry|exit|stop.loss|take.profit)", "trading"),
    (r"(project|milestone|progress|status update|roadmap)", "project"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# 4. TAG EXAMPLES PER TYPE (for validation / reference)
# ═══════════════════════════════════════════════════════════════════════════════

TAG_EXAMPLES = {
    "error":       ["type/error", "status/active", "mcp", "debug", "hermes"],
    "mistake":     ["type/mistake", "status/active", "trading", "risk-management"],
    "decision":    ["type/decision", "status/active", "project/ggscalping", "filter"],
    "concept":     ["type/concept", "status/reference", "zk-proofs", "blockchain"],
    "permanent":   ["type/permanent", "status/active", "knowledge-management", "vault"],
    "analysis":    ["type/analysis", "status/active", "research", "zk-proofs"],
    "comparison":  ["type/comparison", "status/active", "zk-proofs", "starks"],
    "raw":         ["type/raw", "status/reference", "ethereum", "paper"],
    "synthesis":   ["type/synthesis", "status/active", "crypto", "ai-generated"],
    "pattern":     ["type/pattern", "status/active", "trading", "ai-generated"],
    "moc":         ["type/moc", "status/active", "crypto", "index"],
    "connection-report": ["type/connection-report", "status/active", "ai-generated"],
    "entity":      ["type/entity", "status/reference", "vitalik-buterin", "ethereum"],
    "fact":        ["type/fact", "status/reference", "solana", "blockchain"],
    "resource":    ["type/resource", "status/reference", "tutorial", "guide"],
    "tool":        ["type/tool", "status/reference", "mcp", "automation"],
    "prompt":      ["type/prompt", "status/reference", "ai", "template"],
    "daily":       ["type/daily", "status/active", "log"],
    "session":     ["type/session", "status/complete", "debug", "mcp"],
    "trading":     ["type/trading", "status/complete", "sol-usdc", "project/ggscalping"],
    "project":     ["type/project", "status/active", "project/ggscalping", "trading"],
    "note":        ["type/note", "status/active", "general"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# 5. CORE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def extract_tags(content: str, file_path: str = "") -> dict:
    """
    Extract tags from file content using decision tree:
      1. Detect type from frontmatter + content
      2. Extract named entities from frontmatter
      3. Extract topics from content keywords
      4. Detect project
      5. Set default status
      6. Deduplicate and limit (max 5)
    """
    content_lower = content.lower()
    tags = {"topic": [], "status": [], "type": [], "project": []}

    # ── Step 1: Extract from frontmatter ──────────────────────────────────────
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        # Type from frontmatter
        type_match = re.search(r"type:\s*(\w+)", fm)
        if type_match:
            fm_type = type_match.group(1).strip().lower()
            tags["type"].append(fm_type)
        # Status from frontmatter
        status_match = re.search(r"status:\s*(\w+)", fm)
        if status_match:
            fm_status = status_match.group(1).strip().lower()
            tags["status"].append(fm_status)
        # Existing tags from frontmatter
        existing_tags = re.search(r"tags:\s*\[([^\]]+)\]", fm)
        if existing_tags:
            for tag in existing_tags.group(1).split(","):
                tag = tag.strip().lower().replace('"', "").replace("'", "")
                if tag and tag not in tags["topic"]:
                    tags["topic"].append(tag)

    # ── Step 2: Type detection from content (if not in frontmatter) ───────────
    if not tags["type"]:
        for pattern, type_tag in TYPE_INDICATORS:
            if re.search(pattern, content_lower):
                tags["type"].append(type_tag)
                break  # First match wins

    # ── Step 3: Topic extraction from keywords ────────────────────────────────
    for keyword, tag in TOPIC_KEYWORDS.items():
        if keyword in content_lower and tag not in tags["topic"]:
            tags["topic"].append(tag)

    # ── Step 4: Project detection ─────────────────────────────────────────────
    for indicator, project_tag in PROJECT_INDICATORS.items():
        if indicator in content_lower and project_tag not in tags["project"]:
            tags["project"].append(project_tag)

    # ── Step 5: Default status ────────────────────────────────────────────────
    if not tags["status"]:
        tags["status"].append("active")

    # ── Step 6: Deduplicate and limit (max 5) ────────────────────────────────
    all_tags = []
    for cat in ["topic", "type", "status", "project"]:
        all_tags.extend(tags[cat])

    if len(all_tags) > 5:
        priority = []
        # Always include type
        if tags["type"]:
            priority.append(tags["type"][0])
        # Always include status
        if tags["status"]:
            priority.append(tags["status"][0])
        # Include project if present
        if tags["project"] and len(priority) < 5:
            priority.append(tags["project"][0])
        # Fill remaining with topics (up to 5 total)
        for t in tags["topic"]:
            if len(priority) >= 5:
                break
            if t not in priority:
                priority.append(t)
        tags = _rebuild_tags(priority)
    else:
        # Always rebuild: raw fm type/status values must be normalized to
        # prefixed canonical forms (status/X, type/X) or plain tags return.
        tags = _rebuild_tags(all_tags)

    return tags


def _rebuild_tags(tag_list):
    """Rebuild tag structure from flat list."""
    result = {"topic": [], "status": [], "type": [], "project": []}
    status_tags = {"active", "complete", "archived", "waiting", "someday", "reference", "resolved"}
    type_tags = {
        "error", "mistake", "decision", "concept", "permanent",
        "analysis", "comparison", "raw", "synthesis", "pattern",
        "moc", "connection-report", "entity", "fact", "resource",
        "tool", "prompt", "daily", "session", "project", "note", "log", "error-log",
    }
    def _add(cat, val):
        if val not in result[cat]:
            result[cat].append(val)

    for tag in tag_list:
        if tag.startswith("status/") or tag in status_tags:
            _add("status", tag if tag.startswith("status/") else f"status/{tag}")
        elif tag.startswith("type/") or tag in type_tags:
            _add("type", tag if tag.startswith("type/") else f"type/{tag}")
        elif tag.startswith("project/"):
            _add("project", tag)
        else:
            _add("topic", tag)
    return result


def validate_tags(tags: dict) -> list:
    """Validate tags against rules. Returns list of warnings."""
    warnings = []
    all_tags = []
    for cat in ["topic", "type", "status", "project"]:
        all_tags.extend(tags.get(cat, []))

    # Rule 1: Min 2 tags
    if len(all_tags) < 2:
        warnings.append("⚠️ Less than 2 tags — add more topic or type tags")

    # Rule 2: Max 5 tags
    if len(all_tags) > 5:
        warnings.append("⚠️ More than 5 tags — remove least relevant")

    # Rule 3: Type tag required
    if not tags.get("type"):
        warnings.append("⚠️ No type tag — every note needs a type")

    # Rule 4: Status tag required
    if not tags.get("status"):
        warnings.append("⚠️ No status tag — every note needs a status")

    # Rule 5: Topic tag required (at least 1)
    if not tags.get("topic"):
        warnings.append("⚠️ No topic tag — every note needs at least 1 topic")

    # Rule 6: Check for duplicates (case-insensitive)
    seen = set()
    for tag in all_tags:
        lower = tag.lower()
        if lower in seen:
            warnings.append(f"⚠️ Duplicate tag: {tag}")
        seen.add(lower)

    # Rule 7: Check against known examples (soft warning)
    detected_type = tags.get("type", [None])[0] if tags.get("type") else None
    if detected_type and detected_type in TAG_EXAMPLES:
        expected = set(TAG_EXAMPLES[detected_type])
        actual = set(all_tags)
        missing = expected - actual
        if missing and len(missing) >= 3:
            warnings.append(f"ℹ️ Type '{detected_type}' typically has tags: {', '.join(list(missing)[:3])}")

    return warnings


def format_frontmatter(tags: dict, existing_fm: str = None) -> str:
    """Format tags as YAML frontmatter."""
    all_tags = []
    for cat in ["topic", "type", "status", "project"]:
        all_tags.extend(tags.get(cat, []))

    tags_str = ", ".join(all_tags)

    if existing_fm:
        if "tags:" in existing_fm:
            fm = re.sub(
                r"tags:\s*\[[^\]]*\]",
                f"tags: [{tags_str}]",
                existing_fm,
            )
        else:
            fm = existing_fm.rstrip() + f"\ntags: [{tags_str}]\n"
        return fm
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
        return (
            f"---\n"
            f"type: note\n"
            f"status: active\n"
            f"date: {date_str}\n"
            f"tags: [{tags_str}]\n"
            f"---\n"
        )


def apply_tags_to_file(file_path: str, tags: dict) -> bool:
    """Apply tags to file frontmatter. Returns True if successful."""
    try:
        path = Path(file_path)
        if not path.exists():
            print(f"❌ File not found: {file_path}")
            return False

        content = path.read_text(encoding="utf-8")

        fm_match = re.match(r"^(---\s*\n.*?\n---)", content, re.DOTALL)
        if fm_match:
            existing_fm = fm_match.group(1)
            new_fm = format_frontmatter(tags, existing_fm)
            new_content = content.replace(existing_fm, new_fm, 1)
        else:
            new_fm = format_frontmatter(tags)
            new_content = new_fm + "\n" + content

        path.write_text(new_content, encoding="utf-8")
        return True
    except Exception as e:
        print(f"❌ Error applying tags: {e}")
        return False


def check_tag_consistency(file_path: str) -> dict:
    """Check tag consistency for a file. Returns report."""
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    content = path.read_text(encoding="utf-8")
    tags = extract_tags(content, file_path)
    warnings = validate_tags(tags)

    all_tags = []
    for cat in ["topic", "type", "status", "project"]:
        all_tags.extend(tags.get(cat, []))

    return {
        "file": str(path.relative_to(WIKI_ROOT)),
        "tags": tags,
        "all_tags": all_tags,
        "tag_count": len(all_tags),
        "warnings": warnings,
        "valid": len(warnings) == 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 auto-tag.py <file_path>           # Preview tags")
        print("  python3 auto-tag.py <file_path> --apply   # Apply tags to file")
        print("  python3 auto-tag.py <file_path> --check   # Check tag consistency")
        sys.exit(1)

    file_path = sys.argv[1]
    if not Path(file_path).is_absolute():
        # Relative paths are relative to the wiki root (WIKI_ROOT);
        # Path.relative_to() downstream crashes on mixed abs/rel args.
        file_path = str(WIKI_ROOT / file_path)
    apply = "--apply" in sys.argv
    check = "--check" in sys.argv

    path = Path(file_path)
    if not path.exists():
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    if check:
        result = check_tag_consistency(file_path)
        print(json.dumps(result, indent=2))
        sys.exit(0)

    content = path.read_text(encoding="utf-8")
    tags = extract_tags(content, file_path)
    warnings = validate_tags(tags)

    all_tags = []
    for cat in ["topic", "type", "status", "project"]:
        all_tags.extend(tags.get(cat, []))

    result = {
        "file": str(path.relative_to(WIKI_ROOT)),
        "tags": tags,
        "all_tags": all_tags,
        "tag_count": len(all_tags),
        "warnings": warnings,
    }

    print(json.dumps(result, indent=2))

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  {w}")

    if apply:
        if apply_tags_to_file(file_path, tags):
            print(f"\n✅ Tags applied to {file_path}")
        else:
            print(f"\n❌ Failed to apply tags to {file_path}")


if __name__ == "__main__":
    main()
