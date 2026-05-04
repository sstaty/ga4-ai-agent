import asyncio
import json
import os

from anthropic import AsyncAnthropic
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from agent.models import AgentResponse
from agent.prompts import SYSTEM_PROMPT
from agent.tools import EXECUTE_PYTHON_TOOL
from config import settings
from sandbox.runner import run_code

MAX_ITERATIONS = 10
MCP_SERVER_COMMAND = "uvx"
MCP_SERVER_ARGS = ["analytics-mcp"]


def _extract_mcp_text(result) -> str:
    parts = [item.text for item in result.content if hasattr(item, "text")]
    return "\n".join(parts) if parts else "(empty result)"


def _try_parse_rows(text: str) -> list[dict] | None:
    # Only the first parseable MCP result is stored; later GA4 calls won't overwrite raw_data.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list) and all(isinstance(r, dict) for r in parsed):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass
    return None


async def run_agent(question: str) -> AgentResponse:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    server_params = StdioServerParameters(
        command=MCP_SERVER_COMMAND,
        args=MCP_SERVER_ARGS,
        env={
            **os.environ,
            "GOOGLE_APPLICATION_CREDENTIALS": settings.google_application_credentials,
            "GA4_PROPERTY_ID": f"properties/{settings.ga4_property_id}",
        },
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_client:
            await mcp_client.initialize()

            tools_result = await mcp_client.list_tools()
            mcp_tool_defs = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema or {"type": "object", "properties": {}},
                }
                for t in tools_result.tools
            ]
            mcp_tool_names = {t["name"] for t in mcp_tool_defs}
            all_tools = mcp_tool_defs + [EXECUTE_PYTHON_TOOL]

            messages: list = [{"role": "user", "content": question}]
            tool_calls: list[str] = []
            raw_data: list[dict] | None = None
            last_text = ""
            event_loop = asyncio.get_running_loop()

            for iteration in range(1, MAX_ITERATIONS + 1):
                print(f"\n[iter {iteration}] Calling {settings.model}...")

                response = await client.messages.create(
                    model=settings.model,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=all_tools,
                    max_tokens=4096,
                )

                response_text = "".join(
                    block.text for block in response.content
                    if block.type == "text" and block.text
                )
                if response_text:
                    last_text = response_text

                if response.stop_reason == "end_turn":
                    return AgentResponse(
                        answer=last_text or "No response generated.",
                        data=raw_data,
                        tool_calls=tool_calls,
                        iterations=iteration,
                    )

                if response.stop_reason == "tool_use":
                    messages.append({"role": "assistant", "content": response.content})

                    tool_results = []
                    for block in response.content:
                        if block.type != "tool_use":
                            continue

                        tool_name = block.name
                        tool_input = block.input
                        tool_calls.append(tool_name)
                        print(f"[iter {iteration}] tool: {tool_name} | input keys: {list(tool_input.keys())}")

                        if tool_name == "execute_python":
                            result = await event_loop.run_in_executor(
                                None, run_code, tool_input["code"]
                            )
                            content = (
                                f"stdout:\n{result['stdout']}\n"
                                f"stderr:\n{result['stderr']}\n"
                                f"exit_code: {result['exit_code']}"
                            )
                        elif tool_name in mcp_tool_names:
                            mcp_result = await mcp_client.call_tool(tool_name, tool_input)
                            content = _extract_mcp_text(mcp_result)
                            if raw_data is None:
                                raw_data = _try_parse_rows(content)
                        else:
                            content = f"Unknown tool: {tool_name}"

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                        })

                    messages.append({"role": "user", "content": tool_results})

            return AgentResponse(
                answer=last_text or "Max iterations reached without a final answer.",
                data=raw_data,
                tool_calls=tool_calls,
                iterations=MAX_ITERATIONS,
            )
