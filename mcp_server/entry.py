#!/usr/bin/env python3
"""Entry point for semantic-vault MCP server."""
import sys
import os

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from semantic_search_mcp import main

if __name__ == "__main__":
    main()
