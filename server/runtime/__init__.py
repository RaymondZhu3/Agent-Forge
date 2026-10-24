"""Agent runtime (Person 1). Public API for Person 2:

    from server.runtime import run_agent, RunHooks, TEMPLATES
"""

# Load .env before importing the engine: llm.py reads GEMINI_MODEL / GEMINI_TIMEOUT_S / GEMINI_FALLBACK_MODELS
# at import time, and `python -m server.runtime.cli` imports this package before cli.py's own load_dotenv().
# (Live bug: .env said gemini-3.5-flash but every run used the slow default gemini-3.8-flash.)
try:
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from .engine import InMemoryHooks, RunHooks, build_system_prompt, run_agent
from .templates import TEMPLATES

__all__ = ["run_agent", "RunHooks", "InMemoryHooks", "build_system_prompt", "TEMPLATES"]
