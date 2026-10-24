"""The shared tool registry. GET /api/tools returns registry.list_metadata()."""

from .base import ToolRegistry
from .nessie import NESSIE_TOOLS
from .serpapi import SERPAPI_TOOLS

registry = ToolRegistry()
for _tool in [*SERPAPI_TOOLS, *NESSIE_TOOLS]:
    registry.register(_tool)

__all__ = ["registry"]
