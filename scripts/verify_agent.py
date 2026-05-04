#!/usr/bin/env python3
"""Verify the agent loop end-to-end against the real GA4 property.

Run with: uv run python scripts/verify_agent.py

Prints the full AgentResponse for each question. No automated assertions —
inspect the output to confirm the loop works correctly.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.loop import run_agent

QUESTIONS = [
    "How many sessions did we have in the last 7 days?",
    "Which pages get the most traffic? Show me the top 5.",
    "What percentage of our traffic comes from mobile devices? Calculate it.",
]


async def main() -> None:
    for i, question in enumerate(QUESTIONS, 1):
        print(f"\n{'=' * 60}")
        print(f"Question {i}: {question}")
        print("=" * 60)

        response = await run_agent(question)

        print(f"\nAnswer:\n{response.answer}")
        print(f"\nTool calls: {response.tool_calls}")
        print(f"Iterations: {response.iterations}")
        if response.data is not None:
            print(f"Data rows: {len(response.data)}")


if __name__ == "__main__":
    asyncio.run(main())
