import asyncio
import json
import os
import time

from anthropic import AsyncAnthropic
from langfuse import Langfuse
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from agent.models import AgentResponse
from agent.prompts import build_system_prompt
from agent.tools import EXECUTE_PYTHON_TOOL
from config import settings
from sandbox.runner import run_code

MAX_ITERATIONS = 10
MCP_SERVER_COMMAND = "uvx"
MCP_SERVER_ARGS = ["analytics-mcp"]


def _init_langfuse() -> Langfuse | None:
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    try:
        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:
        return None


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


def _serialize_messages(messages: list) -> list[dict]:
    """Convert messages list to JSON-serializable form for Langfuse."""
    out = []
    for msg in messages:
        content = msg["content"]
        if isinstance(content, str):
            out.append({"role": msg["role"], "content": content})
        elif isinstance(content, list):
            items = []
            for item in content:
                if hasattr(item, "model_dump"):
                    items.append(item.model_dump())
                elif isinstance(item, dict):
                    items.append(item)
                else:
                    items.append(str(item))
            out.append({"role": msg["role"], "content": items})
        else:
            out.append({"role": msg["role"], "content": str(content)})
    return out


async def run_agent(question: str) -> AgentResponse:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    lf = _init_langfuse()
    run_start = time.monotonic()
    system_prompt = build_system_prompt(settings.ga4_property_id)

    # Top-level trace — Langfuse v4 creates a trace automatically on the first observation.
    root_obs = lf.start_observation(
        name="run_agent",
        as_type="agent",
        input={"question": question},
        metadata={
            "model": settings.model,
            "ga4_property_id": settings.ga4_property_id,
            "system_prompt": system_prompt,
        },
    ) if lf else None

    server_params = StdioServerParameters(
        command=MCP_SERVER_COMMAND,
        args=MCP_SERVER_ARGS,
        env={
            **os.environ,
            "GOOGLE_APPLICATION_CREDENTIALS": settings.google_application_credentials,
        },
    )

    # Populated in success or error path; written to root_obs in finally.
    trace_output: dict = {}
    trace_metadata: dict = {}

    try:
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
                agent_result: AgentResponse | None = None
                status = "success"

                for iteration in range(1, MAX_ITERATIONS + 1):
                    print(f"\n[iter {iteration}] Calling {settings.model}...")

                    iter_obs = root_obs.start_observation(
                        name=f"iteration-{iteration}",
                        as_type="span",
                    ) if root_obs else None

                    gen_obs = iter_obs.start_observation(
                        name="claude",
                        as_type="generation",
                        model=settings.model,
                        input=_serialize_messages(messages),
                        model_parameters={"max_tokens": 4096},
                    ) if iter_obs else None

                    response = await client.messages.create(
                        model=settings.model,
                        system=system_prompt,
                        messages=messages,
                        tools=all_tools,
                        max_tokens=4096,
                    )

                    if gen_obs:
                        gen_obs.update(
                            output=[b.model_dump() for b in response.content],
                            usage_details={
                                "input": response.usage.input_tokens,
                                "output": response.usage.output_tokens,
                            },
                        )
                        gen_obs.end()

                    response_text = "".join(
                        block.text for block in response.content
                        if block.type == "text" and block.text
                    )
                    if response_text:
                        last_text = response_text

                    if response.stop_reason == "end_turn":
                        agent_result = AgentResponse(
                            answer=last_text or "No response generated.",
                            data=raw_data,
                            tool_calls=tool_calls,
                            iterations=iteration,
                        )
                        if iter_obs:
                            iter_obs.update(output={
                                "stop_reason": "end_turn",
                                "response_text": response_text,
                            })
                            iter_obs.end()
                        break

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

                            tool_obs = iter_obs.start_observation(
                                name=f"tool:{tool_name}",
                                as_type="tool",
                                input=tool_input,
                            ) if iter_obs else None

                            if tool_name == "execute_python":
                                sandbox_result = await event_loop.run_in_executor(
                                    None, run_code, tool_input["code"]
                                )
                                content = (
                                    f"stdout:\n{sandbox_result['stdout']}\n"
                                    f"stderr:\n{sandbox_result['stderr']}\n"
                                    f"exit_code: {sandbox_result['exit_code']}"
                                )
                                if tool_obs:
                                    tool_obs.update(output={
                                        "stdout": sandbox_result["stdout"],
                                        "stderr": sandbox_result["stderr"],
                                        "exit_code": sandbox_result["exit_code"],
                                    })
                                    tool_obs.end()

                            elif tool_name in mcp_tool_names:
                                mcp_result = await mcp_client.call_tool(tool_name, tool_input)
                                content = _extract_mcp_text(mcp_result)
                                if raw_data is None:
                                    raw_data = _try_parse_rows(content)
                                if tool_obs:
                                    tool_obs.update(output={"result": content})
                                    tool_obs.end()

                            else:
                                content = f"Unknown tool: {tool_name}"
                                if tool_obs:
                                    tool_obs.update(output={"error": content})
                                    tool_obs.end()

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": content,
                            })

                        messages.append({"role": "user", "content": tool_results})

                        if iter_obs:
                            iter_obs.update(output={
                                "stop_reason": "tool_use",
                                "response_text": response_text,
                                "tools_called": [b.name for b in response.content if b.type == "tool_use"],
                            })
                            iter_obs.end()

                if agent_result is None:
                    status = "max_iterations"
                    agent_result = AgentResponse(
                        answer=last_text or "Max iterations reached without a final answer.",
                        data=raw_data,
                        tool_calls=tool_calls,
                        iterations=MAX_ITERATIONS,
                    )

                trace_output = {
                    "answer": agent_result.answer,
                    "iterations": agent_result.iterations,
                    "tool_calls": agent_result.tool_calls,
                }
                trace_metadata = {"status": status}
                return agent_result

    except Exception as e:
        trace_output = {"error": str(e)}
        trace_metadata = {"status": "error"}
        raise

    finally:
        if root_obs:
            trace_metadata["total_latency_ms"] = round((time.monotonic() - run_start) * 1000)
            root_obs.update(output=trace_output, metadata=trace_metadata)
            root_obs.end()
        if lf:
            lf.flush()
