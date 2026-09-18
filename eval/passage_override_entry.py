"""Isolated candidate MCP: preserve release routes and shared search/recall.
Capture raw rows during normal retrieval; never perform a second retrieval.
"""
import sys
from contextvars import ContextVar
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import semantic_search_mcp as server
import vault_search_hardened as backend
import passage_reranker_candidate as candidate

_original_search = backend.search_vault
_original_unique = backend.base.unique_rows
_capture = ContextVar('passage_capture', default=None)

def collect(rows, key, distance=False):
    materialized = list(rows)
    capture = _capture.get()
    if capture is not None:
        capture.extend(materialized)
    return _original_unique(materialized, key, distance)

def search(query, top_k=15, mode='broad', strict=False):
    backend.validate(query, top_k, mode)
    if backend.metadata_intent(query) or not query.strip():
        return _original_search(query, top_k, mode, strict)
    # A fixed minimum pool makes quick search and recall share the same prefix.
    limit = min(top_k, 5) if mode == 'quick' else top_k
    chunks = []
    token = _capture.set(chunks)
    try:
        baseline = _original_search(query, max(15, limit), 'broad', strict)
    finally:
        _capture.reset(token)
    return candidate.rerank(query, baseline, chunks, 'combined')[:limit]

backend.base.unique_rows = collect
backend.search_vault = search

if __name__ == '__main__':
    server.main()
