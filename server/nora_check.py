"""Check that your Anthropic key works for NORA.

    python -m server.nora_check

Prints OK and a short answer, or the reason it failed. The key itself is never printed.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from . import nora_llm  # noqa: E402


async def main() -> None:
    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        print("FAILED: ANTHROPIC_API_KEY is empty. Add it to the .env file in the project folder.")
        return
    try:
        data = await nora_llm.post_messages(
            {
                "model": nora_llm.model_name(),
                "max_tokens": 40,
                "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
            }
        )
    except Exception as e:
        print(f"FAILED ({nora_llm.model_name()}): {e}")
        return
    answer = " ".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    print(f"OK ({nora_llm.model_name()}): {answer.strip()}")


if __name__ == "__main__":
    asyncio.run(main())
