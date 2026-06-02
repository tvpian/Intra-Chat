"""
AI engine for Intra-Chat — uses a local Ollama instance by default.

Set the following in your `.env` (or environment) to customise:
    OLLAMA_HOST   = http://localhost:11434   (default)
    OLLAMA_MODEL  = llama3.2                  (default)

If Ollama is unreachable, `summarize_text()` returns a graceful fallback
string instead of raising, so the chat UI never crashes on /summarize.
"""

import os
import requests

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT = int(os.environ.get("OLLAMA_TIMEOUT", "60"))


def summarize_text(text: str, max_length: int = 150, min_length: int = 40) -> str:
    """Summarize text using a local Ollama model.

    `max_length` / `min_length` are word-count hints passed to the model.
    Returns a graceful error string if Ollama is unreachable.
    """
    text = (text or "").strip()
    if not text:
        return "(nothing to summarize)"

    prompt = (
        "Summarize the following chat excerpt in clear, neutral prose. "
        f"Aim for roughly {min_length}-{max_length} words. "
        "Preserve technical commands and file paths verbatim.\n\n"
        f"---\n{text}\n---\n\nSummary:"
    )

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return (data.get("response") or "").strip() or "(empty response from model)"
    except requests.exceptions.ConnectionError:
        return (
            f"[summarize unavailable] Could not reach Ollama at {OLLAMA_HOST}. "
            "Start it with `ollama serve` and pull a model "
            f"(`ollama pull {OLLAMA_MODEL}`)."
        )
    except requests.exceptions.Timeout:
        return f"[summarize timed out after {OLLAMA_TIMEOUT}s]"
    except Exception as exc:
        return f"[summarize error] {exc}"


if __name__ == "__main__":
    sample = (
        "Artificial Intelligence is transforming the way we work and live. "
        "From automating mundane tasks to enabling innovative solutions in "
        "complex domains, AI is evolving at a rapid pace."
    )
    print(summarize_text(sample))
