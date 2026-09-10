import os
from dotenv import load_dotenv

from groq import Groq

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")


def _get_client() -> Groq:
    """Return a Groq client, raising a clear error if the key is missing."""
    if not GROQ_API_KEY or GROQ_API_KEY == "your_actual_key_here":
        raise RuntimeError(
            "GROQ_API_KEY is not configured. "
            "Add your real key to .env and restart the server."
        )
    return Groq(api_key=GROQ_API_KEY)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def test_connection() -> str:
    """Send a simple test message to Groq and return the response text."""
    client = _get_client()
    kwargs = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "user",
                "content": "Reply with exactly: Groq connection successful.",
            }
        ],
        "temperature": 0,
        "max_tokens": 50,
    }
    if "qwen" in GROQ_MODEL.lower():
        kwargs["reasoning_effort"] = "none"

    completion = client.chat.completions.create(**kwargs)
    return completion.choices[0].message.content.strip()

