#!/usr/bin/env python3
"""
session_scan.py — Session scan wrapper script (v2).
Combines auto-tag, connection finder, MOC update, and real-time logging.
Connection finder runs ONCE for all files (not per file).

Requires the companion vault-maintenance scripts in the same SCRIPTS_DIR:
    auto-tag.py, wiki_connection_finder.py, moc_maintenance.py, realtime_log.py
These are part of the broader Semantic Vault tooling (the auto-tag / wiki-connection-finder
utilities). If they are not present, the corresponding steps are skipped with a warning.

Usage:
    python3 session_scan.py --files <file1,file2,...> --topic <topic> [--type <type>]

Paths are read from environment variables with sensible defaults:
    VAULT_ROOT      — your Obsidian vault root            (default: ./vault)
    HERMES_SCRIPTS — dir holding the companion scripts    (default: .)
Override per environment, or edit the two constants below.
"""

import sys
import os
import argparse
import subprocess
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")  # repo root (setup.sh)
from datetime import datetime

WIKI_ROOT = Path(os.getenv("VAULT_ROOT", "./vault"))
SCRIPTS_DIR = Path(os.getenv("HERMES_SCRIPTS", "."))


def run_script(script_name, args, timeout=120):
    """Run a script and return output."""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        print(f"Script not found: {script_path}")
        return None
    cmd = ["python3", str(script_path)] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"{script_name} error: {result.stderr[:100]}")
            return None
    except subprocess.TimeoutExpired:
        print(f"{script_name} timed out")
        return None
    except Exception as e:
        print(f"{script_name} failed: {e}")
        return None


def auto_tag_files(files):
    """Step 4: Auto-tag all files."""
    print("\nStep 4: Auto-tagging files...")
    results = []
    for f in files:
        f = f.strip()
        if not f:
            continue
        if not f.startswith("/"):
            f = str(WIKI_ROOT / f)
        output = run_script("auto-tag.py", [f, "--apply"])
        if output:
            try:
                data = json.loads(output.split("\n")[0])
                results.append(data)
                print(f"  OK {data.get('file', f)}: {data.get('tag_count', 0)} tags")
            except Exception:
                print(f"  OK {f}: tagged")
    return results


def run_connection_finder_once():
    """Step 6: Run connection finder ONCE for all recent files."""
    print("\nStep 6: Running connection finder (once)...")
    output = run_script("wiki_connection_finder.py", [], timeout=180)
    if output:
        for line in output.split("\n"):
            if any(k in line.lower() for k in ["strong", "medium", "weak", "contradiction", "done"]):
                print(f"  {line.strip()}")


def update_moc_for_topic(topic):
    """Step 7: Update MOC for topic (once)."""
    print(f"\nStep 7: Updating MOC for '{topic}'...")
    topic_lower = topic.lower().replace("-", " ").replace("_", " ")
    moc_file = WIKI_ROOT / "07-INDEX" / f"MOC-{topic}.md"
    if moc_file.exists():
        output = run_script("moc_maintenance.py", ["--update", str(moc_file)])
        if output:
            print(f"  {output.strip()}")
    else:
        print(f"  MOC-{topic}.md not found (create manually if needed)")


def log_to_daily_note(topic, files, scan_type):
    """Step 9: Log to daily note."""
    print("\nStep 9: Logging to daily note...")
    files_str = ",".join([f.strip() for f in files if f.strip()])
    result = run_script("realtime_log.py", [
        "--type", scan_type,
        "--title", f"Session scan: {topic}",
        "--files", files_str,
        "--result", f"{len(files)} files",
    ])
    if result and "Logged" in result:
        print("  Logged to daily note")


def generate_report(topic, files):
    """Step 11: Generate summary report."""
    print("\n" + "=" * 60)
    print(f"Session Scan Complete: {topic}")
    print("=" * 60)
    print(f"\nFiles: {len(files)}")
    for f in files:
        if f.strip():
            print(f"  - {f.strip()}")

    date_str = datetime.now().strftime("%Y-%m-%d")
    conn_report = WIKI_ROOT / "04-LOGS" / "reports" / f"{date_str}-connections-report.md"
    if conn_report.exists():
        print(f"\nConnection report: {conn_report.relative_to(WIKI_ROOT)}")
    daily_note = WIKI_ROOT / "04-LOGS" / "daily-note" / f"{date_str}.md"
    if daily_note.exists():
        print(f"Daily note: {daily_note.relative_to(WIKI_ROOT)}")
    print(f"\nCompleted at: {datetime.now().strftime('%H:%M:%S')}")


def main():
    parser = argparse.ArgumentParser(description="Session scan wrapper v2")
    parser.add_argument("--files", required=True, help="Comma-separated file paths")
    parser.add_argument("--topic", required=True, help="Topic of the session")
    parser.add_argument("--type", default="session-scan", help="Scan type")

    args = parser.parse_args()
    files = [f.strip() for f in args.files.split(",") if f.strip()]
    topic = args.topic
    scan_type = args.type

    print(f"Session Scan: {topic} ({scan_type})")
    print(f"Files: {len(files)}")

    # Step 4: Auto-tag all files
    auto_tag_files(files)

    # Step 6: Connection finder (ONCE for all files)
    run_connection_finder_once()

    # Step 7: MOC update (once for topic)
    update_moc_for_topic(topic)

    # Step 9: Log to daily note
    log_to_daily_note(topic, files, scan_type)

    # Step 11: Report
    generate_report(topic, files)


if __name__ == "__main__":
    main()
