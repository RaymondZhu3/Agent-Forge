"""Agent runtime (Person 1). Public API for Person 2:

    from server.runtime import run_agent, RunHooks, TEMPLATES
"""

from .engine import InMemoryHooks, RunHooks, build_system_prompt, run_agent
from .templates import TEMPLATES

__all__ = ["run_agent", "RunHooks", "InMemoryHooks", "build_system_prompt", "TEMPLATES"]
