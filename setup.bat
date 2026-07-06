@echo off
setlocal enabledelayedexpansion

echo ============================================
echo  Semantic Vault RAG — Setup (Windows)
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ first.
    pause
    exit /b 1
)

:: Create venv
if not exist "venv\" (
    echo [1/4] Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat

:: Install deps
echo [2/4] Installing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

:: Check Ollama
echo [3/4] Checking Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Ollama not running at localhost:11434
    echo        Start Ollama first, then run:
    echo        ollama pull bge-m3
) else (
    echo Ollama is running.
    echo Pulling embedding model (bge-m3)...
    ollama pull bge-m3
)

:: Copy env example
if not exist ".env" (
    echo [4/4] Creating .env from .env.example...
    copy .env.example .env
    echo [IMPORTANT] Edit .env and set VAULT_ROOT to your vault path!
)

echo.
echo ============================================
echo  Setup complete!
echo.
echo  Next steps:
echo  1. Edit .env - set VAULT_ROOT to your Obsidian vault path
echo  2. Run: python indexer\vault_indexer.py --once
echo  3. Add MCP config to Claude Desktop/Hermes (see README.md)
echo ============================================
pause
