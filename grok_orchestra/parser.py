"""Orchestra spec parser — extends the Grok Build Bridge spec parser.

Bridge ships a parser for single-agent build specs; Orchestra layers role,
pattern, and veto-gate fields on top. All Bridge fields remain valid so that
an Orchestra spec is a strict superset of a Bridge spec.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_spec(path: str | Path) -> dict[str, Any]:
    """Load and validate an Orchestra spec from ``path``.

    Parameters
    ----------
    path:
        Filesystem path to a YAML or JSON orchestra spec.

    Returns
    -------
    dict[str, Any]
        The parsed spec, already validated against the Orchestra schema.
    """
    raise NotImplementedError("session 2")


def parse(source: str | dict[str, Any]) -> dict[str, Any]:
    """Parse an Orchestra spec from a raw string or dict.

    This is the non-filesystem counterpart to :func:`load_spec` and is intended
    for callers that already have the spec in memory (e.g. notebooks, tests).
    """
    raise NotImplementedError("session 2")
