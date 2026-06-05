from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP

from rag.tools.tavily_search import search_web

mcp = FastMCP("tavily")


@mcp.tool()
def search_web_tool(query: str) -> str:
    """使用 Tavily 搜索互联网公开信息，返回结构化 JSON。"""
    return json.dumps(search_web(query), ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
