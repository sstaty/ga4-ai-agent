#!/usr/bin/env python3
"""Verify GA4 MCP connectivity using the Anthropic SDK MCP client.

Prerequisites:
  1. Create a .env file from .env.example and fill in your credentials.
  2. Install the GA4 MCP server.
  3. Update MCP_SERVER_COMMAND / MCP_SERVER_ARGS below if your server
     uses a different invocation.

The script connects to the MCP server over stdio, lists available tools,
then asks Claude a simple question about the configured GA4 property.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from anthropic import AsyncAnthropic
from anthropic.lib.tools.mcp import async_mcp_tool
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from config import settings

MCP_SERVER_COMMAND = "uvx"
MCP_SERVER_ARGS = ["analytics-mcp"]


async def main() -> None:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    server_env = {
        **os.environ,
        "GOOGLE_APPLICATION_CREDENTIALS": settings.google_application_credentials,
        "GA4_PROPERTY_ID": f"properties/{settings.ga4_property_id}",
    }

    server_params = StdioServerParameters(
        command=MCP_SERVER_COMMAND,
        args=MCP_SERVER_ARGS,
        env=server_env,
    )

    print(f"Connecting to GA4 MCP server ({MCP_SERVER_COMMAND} {' '.join(MCP_SERVER_ARGS)})...")

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_client:
            await mcp_client.initialize()

            tools_result = await mcp_client.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"Available MCP tools: {tool_names}\n")

            question = (
                f"How many active users did GA4 property {settings.ga4_property_id} "
                f"receive in the last 28 days?"
            )
            print(f"Question: {question}\n")

            runner = client.beta.messages.tool_runner(
                model="claude-opus-4-7",
                max_tokens=1024,
                messages=[{"role": "user", "content": question}],
                tools=[async_mcp_tool(t, mcp_client) for t in tools_result.tools],
            )

            print("Response:")
            async for message in runner:
                for block in message.content:
                    if block.type == "text":
                        print(block.text)

    print("\nGA4 MCP verification complete.")


if __name__ == "__main__":
    asyncio.run(main())
