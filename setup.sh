#!/usr/bin/env bash
set -euo pipefail

echo "============================================"
echo " Semantic Vault RAG — Setup (Linux/Mac)"
echo "============================================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] Python 3 not found. Install Python 3.10+ first."
    exit 1
fi

# Create venv
if [ ! -d "venv" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate

# Install deps
echo "[2/4] Installing Python dependencies..."
pip install -r requirements.txt

# Check Ollama
echo "[3/4] Checking Ollama..."
if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama is running. Pulling embedding model (bge-m3)..."
    ollama pull bge-m3
else
    echo "[WARN] Ollama not running at localhost:11434"
    echo "       Start Ollama first, then run: ollama pull bge-m3"
fi

# Copy env example
if [ ! -f ".env" ]; then
    echo "[4/4] Creating .env from .env.example..."
    cp .env.example .env
    echo "[IMPORTANT] Edit .env and set VAULT_ROOT to your vault path!"
fi

echo ""
echo "============================================"
echo " Setup complete!"
echo ""
echo " Next steps:"
echo "  1. Edit .env - set VAULT_ROOT to your vault path"
echo "  2. Run: python indexer/vault_indexer.py --once"
echo "  3. Add MCP config to Claude Desktop/Hermes (see README.md)"
echo "============================================"
