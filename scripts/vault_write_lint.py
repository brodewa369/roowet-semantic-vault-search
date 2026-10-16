#!/usr/bin/env python3
"""vault_write_lint.py — deterministic post-write check for the Claim Update Gate.

R1 (dual state):   a new evergreen/state file whose entity tokens overlap an older
                   evergreen owner file in state-type folders (>= 50% match).
R2 (orphan incident): a new dated incident file (error/lesson/decision/blocker/
                   correction/knowledge-gap/pattern) with no [[backlink]] anywhere.

Usage: python vault_write_lint.py [window_days]
Exit 0 = clean, 1 = violations. Read-only. Point VAULT_ROOT at your vault.
"""
import os, re, sys, datetime

STATE_DIRS = ("05-PROJECT/active/", "05-PROJECT/archive/", "02-KNOWLEDGE/entities/",
              "02-KNOWLEDGE/concepts/", "01-AGENT-MEMORY/tools/", "08-BRODEWA-HERMES-SYSTEM/")
INCIDENT_DIRS = ("01-AGENT-MEMORY/error-log/", "01-AGENT-MEMORY/lessons-learned/",
                 "01-AGENT-MEMORY/decisions/", "01-AGENT-MEMORY/blockers/",
                 "01-AGENT-MEMORY/corrections/", "01-AGENT-MEMORY/knowledge-gaps/",
                 "01-AGENT-MEMORY/patterns/")

VAULT = os.getenv("VAULT_ROOT", "./vault")

def rel(p): return os.path.relpath(p, VAULT).replace("\\", "/")

def is_state(p):
    r = rel(p)
    return any(r.startswith(x) for x in STATE_DIRS) and os.path.basename(p) != "LOG.md"

def is_incident(p):
    r = rel(p)
    return any(r.startswith(x) for x in INCIDENT_DIRS)

def mtime_date(p): return datetime.date.fromtimestamp(os.path.getmtime(p))

def entity_tokens(name):
    stop = {"", "md", "log", "index", "overview", "the", "and", "of", "id"}
    toks = [t for t in re.split(r"[^a-zA-Z0-9]+", name.lower())
            if len(t) > 2 and t not in stop]
    return [t for t in toks if not re.fullmatch(r"20\d{2}", t)]

def main(window_days=0):
    start = datetime.date.today() - datetime.timedelta(days=window_days)
    new_files, violations = [], []
    for root, dirs, files in os.walk(VAULT):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.endswith(".md"):
                p = os.path.join(root, f)
                try:
                    if mtime_date(p) >= start:
                        new_files.append(p)
                except OSError:
                    pass
    for p in new_files:
        base = os.path.basename(p)
        if is_incident(p) and re.search(r"\d{4}-\d{2}-\d{2}", base):
            try:
                content = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            if not re.search(r"\[\[[^\]]+\]\]", content):
                violations.append(("R2", rel(p), "incident file has no [[owner backlink]] anywhere"))
        if is_state(p):
            toks = set(entity_tokens(base))
            if not toks:
                continue
            for root2, dirs2, files2 in os.walk(VAULT):
                dirs2[:] = [d for d in dirs2 if not d.startswith(".")]
                for f2 in files2:
                    if not f2.endswith(".md"):
                        continue
                    q = os.path.join(root2, f2)
                    if q == p or not is_state(q) or re.search(r"\d{4}-\d{2}-\d{2}", f2):
                        continue
                    qt = set(entity_tokens(f2))
                    if qt and len(toks & qt) / max(1, len(toks)) >= 0.5:
                        if mtime_date(q) < mtime_date(p):
                            violations.append(("R1", rel(p),
                                f"possible SECOND state file — older owner shares tokens: {rel(q)}"))
    print(f"window: files modified since {start} (inclusive) -> scanned {len(new_files)} new files")
    if violations:
        print(f"VIOLATIONS: {len(violations)}")
        for r, f, why in violations:
            print(f"  [{r}] {f} — {why}")
        return 1
    print("CLEAN — no Claim Update Gate violations found")
    return 0

if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    sys.exit(main(days))
