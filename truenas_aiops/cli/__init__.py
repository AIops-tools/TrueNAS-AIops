"""CLI package for truenas-aiops.

Re-exports ``app`` so the pyproject entry point
``truenas-aiops = "truenas_aiops.cli:app"`` works unchanged.
"""

from truenas_aiops.cli._root import app

__all__ = ["app"]
