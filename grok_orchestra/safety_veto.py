"""The Lucas veto gate.

Lucas is the safety-reviewer role. Any agent-authored side effect (posting to
X, opening a PR, shipping a build artefact) has to pass a Lucas veto before
the dispatcher releases it. The gate composes Bridge's :func:`audit_x_post`
with Orchestra-specific policy checks so that both native and simulated
runtimes share exactly the same approval path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VetoDecision:
    """Outcome of a :class:`LucasVeto` review."""

    approved: bool
    reason: str
    reviewer: str = "Lucas"


class LucasVeto:
    """Safety gate applied to agent-authored side effects."""

    def __init__(self, *, strict: bool = True) -> None:
        self.strict = strict

    async def review(self, action: dict[str, Any]) -> VetoDecision:
        """Review ``action`` and return a :class:`VetoDecision`.

        Parameters
        ----------
        action:
            A dict describing the proposed side effect (e.g. an X post draft,
            a git diff, a shell command).
        """
        raise NotImplementedError("session 6")
