"""
vault_indexer.py — Semantic Indexer for Obsidian Vault
- Watch vault folder for .md file changes
- Chunk files by section (## headers)
- Embed chunks via Ollama embedding models
- Store vectors in LanceDB
- Auto-reindex on file change

V2 — True batch embedding via /api/embed
  - Sends up to 50 chunks per HTTP call instead of 1
  - ~30-50x faster than serial embedding
  - Recursive batch splitting on timeout
  - All paths configurable via env vars (see .env.example)
"""

import os
import sys
import time
import hashlib
import logging
import threading
import msvcrt
from pathlib import Path
from datetime import datetime

# ── Config (env-var driven) ─────────────────────────────────────────────────

VAULT_ROOT = os.getenv("VAULT_ROOT", "./vault")
LANCEDB_PATH = os.getenv("LANCEDB_PATH", "./data/lancedb")
_db_dir = os.path.dirname(LANCEDB_PATH) if os.path.dirname(LANCEDB_PATH) else "."
HASH_STORE_PATH = os.getenv("HASH_STORE_PATH", os.path.join(_db_dir, "vault_indexer_hashes.json"))
LOCK_FILE = os.getenv("LOCK_FILE", os.path.join(_db_dir, "vault_indexer.lock"))
BACKUP_DIR = os.getenv("BACKUP_DIR", os.path.join(_db_dir, "backups"))
LOG_DIR = os.getenv("LOG_DIR", _db_dir)
MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", "2"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "512"))
OVERLAP = int(os.getenv("OVERLAP", "64"))
WATCH_INTERVAL = int(os.getenv("WATCH_INTERVAL", "5"))
EXCLUDE_DIRS = set(os.getenv("EXCLUDE_DIRS", ".obsidian,.trash,.git,__pycache__").split(","))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))

# ── Logging ──────────────────────────────────────────────────────────────────

_log_file = os.path.join(LOG_DIR, "vault_indexer.log")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_log_file),
    ],
)
log = logging.getLogger("vault_indexer")

# ── Instance Lock ─────────────────────────────────────────────────────────────

_lock_fh = None

def acquire_lock():
    global _lock_fh
    try:
        _lock_fh = open(LOCK_FILE, 'w')
        msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
        log.info(f"Instance lock acquired (PID: {os.getpid()})")
    except OSError:
        log.error("Another instance already running. Exiting.")
        sys.exit(0)

def release_lock():
    global _lock_fh
    if _lock_fh:
        try:
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
            _lock_fh.close()
        except Exception:
            pass
        try:
            os.remove(LOCK_FILE)
        except Exception:
            pass
        _lock_fh = None

# ── Imports ───────────────────────────────────────────────────────────────────

try:
    import lancedb
    import pyarrow as pa
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import requests
except ImportError as e:
    log.error(f"Missing dependency: {e}")
    log.error("Install: pip install lancedb pyarrow watchdog requests")
    sys.exit(1)


# ── Embedder — True Batch via /api/embed ─────────────────────────────────────

class OllamaEmbedder:
    def __init__(self, url: str = OLLAMA_BASE_URL, model: str = EMBED_MODEL):
        self.url = url
        self.model = model
        self._consecutive_failures = 0
        self._circuit_open = False
        self._circuit_open_until = 0
        self._check_connection()

    def _check_connection(self):
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=5)
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                if self.model not in models and f"{self.model}:latest" not in models:
                    log.warning(f"Model {self.model} not found. Available: {models}")
                    log.info(f"Run: ollama pull {self.model}")
                else:
                    log.info(f"Ollama connected. Model {self.model} ready.")
        except requests.ConnectionError:
            log.error("Ollama not running. Start with: ollama serve")

    def _is_circuit_open(self) -> bool:
        if self._circuit_open:
            if time.time() < self._circuit_open_until:
                return True
            else:
                log.info("Circuit breaker: retrying Ollama...")
                self._circuit_open = False
                self._consecutive_failures = 0
        return False

    def _record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= 5:
            self._circuit_open = True
            self._circuit_open_until = time.time() + 60
            log.error("Ollama down — circuit open. Pausing 60s before retry.")

    def embed(self, text: str) -> list[float]:
        """Single text embedding — used by search()."""
        if self._is_circuit_open():
            return []
        try:
            r = requests.post(
                f"{self.url}/api/embed",
                json={"model": self.model, "input": [text]},
                timeout=30,
            )
            if r.status_code == 200:
                self._consecutive_failures = 0
                return r.json()["embeddings"][0]
            else:
                log.error(f"Embed failed: {r.status_code} {r.text[:200]}")
                self._record_failure()
                return []
        except Exception as e:
            log.error(f"Embed error: {e}")
            self._record_failure()
            return []

    def embed_batch(self, texts: list[str], batch_size: int = BATCH_SIZE) -> list[list[float]]:
        """
        True batch embedding — sends multiple texts per HTTP call.
        Returns list of embeddings (one per input text).
        Empty list [] for any text that failed.
        """
        if self._is_circuit_open():
            return [[] for _ in texts]

        all_embeddings = [[] for _ in texts]

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_indices = list(range(i, min(i + batch_size, len(texts))))

            for attempt in range(3):
                try:
                    r = requests.post(
                        f"{self.url}/api/embed",
                        json={"model": self.model, "input": batch},
                        timeout=120,
                    )
                    if r.status_code == 200:
                        embeddings = r.json()["embeddings"]
                        self._consecutive_failures = 0
                        for idx, emb in zip(batch_indices, embeddings):
                            all_embeddings[idx] = emb
                        log.info(f"  Batch {i // batch_size + 1}: embedded {len(batch)} chunks")
                        break
                    else:
                        log.error(f"Batch embed failed: {r.status_code}")
                        self._record_failure()
                except requests.Timeout:
                    log.warning(f"Batch timeout (attempt {attempt + 1}/3), splitting batch...")
                    if len(batch) > 1:
                        mid = len(batch) // 2
                        left = self.embed_batch(texts[i:i + mid], batch_size=batch_size)
                        right = self.embed_batch(texts[i + mid:i + len(batch)], batch_size=batch_size)
                        for idx, emb in enumerate(left):
                            all_embeddings[i + idx] = emb
                        for idx, emb in enumerate(right):
                            all_embeddings[i + mid + idx] = emb
                        break
                    else:
                        log.error("Single chunk timeout, skipping")
                        self._record_failure()
                except Exception as e:
                    log.error(f"Batch embed error: {e}")
                    self._record_failure()
                    if attempt < 2:
                        time.sleep((attempt + 1) * 3)

            if self._is_circuit_open():
                break

        return all_embeddings


# ── Chunker ───────────────────────────────────────────────────────────────────

def chunk_file(content: str, filepath: str) -> list[dict]:
    """Split markdown content into chunks by ## headers."""
    chunks = []

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            content = parts[2]

    sections = content.split("\n## ")

    for i, section in enumerate(sections):
        if i == 0:
            text = section.strip()
        else:
            text = "## " + section.strip()

        if not text.strip():
            continue

        if len(text) > CHUNK_SIZE * 2:
            words = text.split()
            current = []
            current_len = 0
            for word in words:
                current.append(word)
                current_len += len(word) + 1
                if current_len >= CHUNK_SIZE:
                    chunk_text = " ".join(current)
                    chunks.append({
                        "text": chunk_text,
                        "source": filepath,
                        "chunk_id": hashlib.md5(chunk_text.encode()).hexdigest(),
                    })
                    overlap_words = current[-OVERLAP // 4:]
                    current = overlap_words
                    current_len = sum(len(w) + 1 for w in overlap_words)
            if current:
                chunk_text = " ".join(current)
                chunks.append({
                    "text": chunk_text,
                    "source": filepath,
                    "chunk_id": hashlib.md5(chunk_text.encode()).hexdigest(),
                })
        else:
            chunks.append({
                "text": text,
                "source": filepath,
                "chunk_id": hashlib.md5(text.encode()).hexdigest(),
            })

    return chunks


# ── Indexer ───────────────────────────────────────────────────────────────────

class VaultIndexer:
    def __init__(self):
        self._is_indexing = False
        self.embedder = OllamaEmbedder()
        self.db = lancedb.connect(LANCEDB_PATH)
        self._init_table()
        self.file_hashes: dict[str, str] = {}
        self._load_existing_hashes()

    def _init_table(self):
        import shutil
        lance_path = os.path.join(LANCEDB_PATH, "vault_chunks.lance")

        schema = pa.schema([
            pa.field("chunk_id", pa.string()),
            pa.field("source", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), 1024)),
            pa.field("indexed_at", pa.string()),
        ])

        try:
            self.table = self.db.open_table("vault_chunks")
            _ = len(self.table)
            log.info(f"Opened existing table. Rows: {len(self.table)}")
        except Exception:
            if os.path.exists(lance_path):
                shutil.rmtree(lance_path, ignore_errors=True)
            self.table = self.db.create_table("vault_chunks", schema=schema, mode="create")
            log.info("Created new vault_chunks table")

    def _load_existing_hashes(self):
        import json
        try:
            if Path(HASH_STORE_PATH).exists():
                with open(HASH_STORE_PATH, "r") as f:
                    self.file_hashes = json.load(f)
                log.info(f"Loaded {len(self.file_hashes)} hashes from persistent storage")
        except Exception as e:
            log.warning(f"Failed to load hash store: {e}")
            self.file_hashes = {}

    def _sync_deleted_files(self):
        """Remove hashes and LanceDB chunks for files that no longer exist."""
        try:
            stale = [fp for fp in self.file_hashes if not Path(fp).exists()]
            for fp in stale:
                try:
                    self.table.delete(f"source = '{fp.replace(chr(39), chr(39)+chr(39))}'")
                except Exception:
                    pass
                del self.file_hashes[fp]
                log.info(f"Cleaned up deleted file: {fp}")
            if stale:
                self._save_hashes()
                log.info(f"Cleaned up {len(stale)} stale entries")
        except Exception as e:
            log.warning(f"Failed to sync deleted files: {e}")

    def _backup_index(self):
        import shutil
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            dst = os.path.join(BACKUP_DIR, f'vault_vectors_{ts}')
            if os.path.isdir(LANCEDB_PATH):
                shutil.copytree(src=LANCEDB_PATH, dst=dst)
                if os.path.isfile(HASH_STORE_PATH):
                    shutil.copy2(HASH_STORE_PATH, os.path.join(BACKUP_DIR, f'vault_indexer_hashes_{ts}.json'))
                log.info(f"Backup created: {dst}")
                self._cleanup_old_backups()
            else:
                log.warning("No vault_vectors directory to backup")
        except Exception as e:
            log.warning(f"Backup failed: {e}")

    def _cleanup_old_backups(self):
        import shutil
        try:
            if not os.path.isdir(BACKUP_DIR):
                return
            dirs = sorted(
                [d for d in os.listdir(BACKUP_DIR) if d.startswith("vault_vectors_")],
                reverse=True
            )
            for old in dirs[MAX_BACKUPS:]:
                old_path = os.path.join(BACKUP_DIR, old)
                if os.path.isdir(old_path):
                    shutil.rmtree(old_path)
                    log.info(f"Cleaned old backup: {old}")
            hash_files = sorted(
                [f for f in os.listdir(BACKUP_DIR) if f.startswith("vault_indexer_hashes_")],
                reverse=True
            )
            for old_h in hash_files[MAX_BACKUPS:]:
                os.remove(os.path.join(BACKUP_DIR, old_h))
        except Exception as e:
            log.warning(f"Backup cleanup failed: {e}")

    def _save_hashes(self):
        import json, tempfile
        try:
            dir_path = Path(HASH_STORE_PATH).parent
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".json")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self.file_hashes, f, indent=2)
                os.replace(tmp_path, HASH_STORE_PATH)
            except Exception:
                os.unlink(tmp_path)
                raise
        except Exception as e:
            log.warning(f"Failed to save hash store: {e}")

    def _file_hash(self, filepath: str) -> str:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return hashlib.md5(f.read().encode()).hexdigest()
        except Exception:
            return ""

    def index_file(self, filepath: str) -> int:
        """Index a single file. Returns number of chunks indexed."""
        filepath = str(Path(filepath).resolve())

        if not filepath.endswith(".md"):
            return 0

        for excl in EXCLUDE_DIRS:
            if excl in filepath:
                return 0

        new_hash = self._file_hash(filepath)
        if not new_hash:
            return 0
        if filepath in self.file_hashes and self.file_hashes[filepath] == new_hash:
            return 0

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            log.error(f"Read error {filepath}: {e}")
            return 0

        if not content.strip():
            return 0

        try:
            self.table.delete(f"source = '{filepath.replace(chr(39), chr(39)+chr(39))}'")
        except Exception:
            pass

        chunks = chunk_file(content, filepath)
        if not chunks:
            return 0

        # True batch embedding
        texts = [c["text"] for c in chunks]
        vectors = self.embedder.embed_batch(texts, batch_size=BATCH_SIZE)

        valid = []
        for chunk, vec in zip(chunks, vectors):
            if vec:
                valid.append({
                    "chunk_id": chunk["chunk_id"],
                    "source": chunk["source"],
                    "text": chunk["text"][:1024],
                    "vector": vec,
                    "indexed_at": datetime.now().isoformat(),
                })

        if valid:
            self.table.add(valid)
            self.file_hashes[filepath] = new_hash
            self._save_hashes()
            log.info(f"Indexed {len(valid)} chunks from {Path(filepath).name}")
            return len(valid)

        return 0

    def index_vault(self) -> int:
        """Index entire vault. Returns total chunks indexed."""
        self._is_indexing = True
        self._backup_index()
        self._sync_deleted_files()
        total = 0
        md_files = [
            f for f in Path(VAULT_ROOT).rglob("*.md")
            if not any(excl in str(f) for excl in EXCLUDE_DIRS)
        ]
        log.info(f"Found {len(md_files)} .md files in vault")

        for filepath in md_files:
            try:
                n = self.index_file(str(filepath))
                total += n
            except Exception as e:
                log.error(f"Index error {filepath}: {e}")

        log.info(f"Total chunks indexed: {total}")
        self._is_indexing = False
        return total

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Semantic search. Returns top K matching chunks."""
        vec = self.embedder.embed(query)
        if not vec:
            return []

        results = (
            self.table.search(vec)
            .limit(top_k)
            .to_list()
        )

        return [
            {
                "source": r["source"],
                "text": r["text"][:300],
                "score": r.get("_distance", 0),
            }
            for r in results
        ]

    def stats(self) -> dict:
        try:
            count = len(self.table)
            sources = self.table.to_pandas()["source"].nunique() if count > 0 else 0
            return {"total_chunks": count, "unique_files": sources}
        except Exception:
            return {"total_chunks": 0, "unique_files": 0}


# ── File Watcher ──────────────────────────────────────────────────────────────

class VaultHandler(FileSystemEventHandler):
    def __init__(self, indexer: VaultIndexer):
        self.indexer = indexer
        self._debounce: dict[str, float] = {}
        self._lock = threading.Lock()

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            self._handle(event.src_path)

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            self._handle(event.src_path)

    def _handle(self, filepath: str):
        if self.indexer._is_indexing:
            return

        for excl in EXCLUDE_DIRS:
            if excl in filepath:
                return

        now = time.time()
        with self._lock:
            last = self._debounce.get(filepath, 0)
            if now - last < 5:
                return
            self._debounce[filepath] = now

        log.info(f"File changed: {Path(filepath).name}")
        try:
            self.indexer.index_file(filepath)
        except Exception as e:
            log.error(f"Watch handler error: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Vault Semantic Indexer")
    parser.add_argument("--once", action="store_true",
                        help="Run full index once and exit")
    parser.add_argument("--watch", action="store_true", default=False,
                        help="Run as continuous file watcher daemon")
    parser.add_argument("--reindex", action="store_true",
                        help="Force full re-index, clear existing data")
    parser.add_argument("--daemon", action="store_true", default=False,
                        help="Run as file watcher daemon (legacy mode)")
    args = parser.parse_args()

    acquire_lock()

    try:
        log.info("=" * 60)
        log.info("Vault Semantic Indexer v2 starting (batch embedding)")
        log.info(f"Vault: {VAULT_ROOT}")
        log.info(f"LanceDB: {LANCEDB_PATH}")
        log.info(f"Embed: {EMBED_MODEL} via {OLLAMA_BASE_URL}")
        log.info(f"Batch size: {BATCH_SIZE}")
        log.info(f"Mode: {'daemon' if args.watch or args.daemon else 'one-shot'}")
        log.info("=" * 60)

        indexer = VaultIndexer()

        if args.reindex:
            log.info("Force re-index: clearing all existing chunks and hashes...")
            try:
                indexer.table.delete("1=1")
                indexer.file_hashes = {}
                indexer._save_hashes()
                log.info("Cleared")
            except Exception as e:
                log.warning(f"Clear failed: {e}")

        log.info("Running full vault index...")
        t0 = time.time()
        total = indexer.index_vault()
        elapsed = time.time() - t0
        log.info(f"Index complete: {total} chunks in {elapsed:.1f}s")

        if args.once or (not args.watch and not args.daemon):
            log.info("One-shot mode — exiting")
            return

        handler = VaultHandler(indexer)
        observer = Observer()
        observer.schedule(handler, VAULT_ROOT, recursive=True)
        observer.start()
        log.info(f"Watching {VAULT_ROOT} for changes...")

        try:
            while True:
                time.sleep(WATCH_INTERVAL)
        except KeyboardInterrupt:
            log.info("Shutting down...")
            observer.stop()
        observer.join()

    finally:
        release_lock()


if __name__ == "__main__":
    main()
