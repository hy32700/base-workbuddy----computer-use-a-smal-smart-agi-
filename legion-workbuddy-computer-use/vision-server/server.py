"""WorkBuddy-native vision/chat coordination MCP. No external model API."""

import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult
from bridge import call
from tools import TOOLS

server = Server('desktop-coordinator')


@server.list_tools()
async def list_tools():
    return TOOLS


@server.call_tool()
async def call_tool(name, arguments):
    result = await asyncio.to_thread(call, name, arguments)
    return CallToolResult.model_validate(result)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == '__main__':
    asyncio.run(main())
