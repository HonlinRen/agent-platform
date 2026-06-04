from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

async def load_mcp_tools_async() -> list[StructuredTool]:
    command = os.environ.get("MCP_WHITEPAPER_COMMAND", "").strip()
    if not command:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        parts = command.split()
        client = MultiServerMCPClient(
            {
                "whitepaper": {
                    "command": parts[0],
                    "args": parts[1:],
                    "transport": "stdio",
                }
            }
        )
        return await client.get_tools()
    except Exception as exc:
        logger.warning("MCP tools unavailable: %s", exc)
        return []


def load_mcp_tools() -> list[StructuredTool]:
    try:
        return asyncio.run(load_mcp_tools_async())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(load_mcp_tools_async())
        finally:
            loop.close()
