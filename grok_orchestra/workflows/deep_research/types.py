"""Core data shapes for the Deep Research workflow.

Kept in their own module so the planner, workflow, and tests can
import them without pulling in the LLM-call layer. Frozen dataclasses
+ enums are JSON-serialisable round-trip via :mod:`...plan`.
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "SourceRoute",
    "SubQuestion",
    "SubQuestionStatus",
]


class SourceRoute(str, enum.Enum):
    """Where a sub-question's answer should come from.

    The planner returns one or more of these per sub-question, based on
    the question's reasoning. 15b will dispatch matching sub-questions
    to the matching :class:`grok_orchestra.sources.Source`.
    """

    WEB = "web"
    LOCAL = "local"
    MCP = "mcp"
    REASONING = "reasoning"   # answerable from prior context, no source needed

    @classmethod
    def coerce(cls, value: Any) -> SourceRoute:
        """Lenient coercion for LLM-generated source labels."""
        if isinstance(value, SourceRoute):
            return value
        s = str(value or "").strip().lower()
        if s in {"web", "search", "internet", "tavily", "google"}:
            return cls.WEB
        if s in {"local", "local_docs", "docs", "pdf", "file"}:
            return cls.LOCAL
        if s in {"mcp", "github", "postgres", "internal"}:
            return cls.MCP
        return cls.REASONING


class SubQuestionStatus(str, enum.Enum):
    """Per-node lifecycle. Only the planner sets ``planned``; later
    workflows mutate to ``in_progress`` / ``answered`` / ``failed`` /
    ``skipped``."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    ANSWERED = "answered"
    FAILED = "failed"
    SKIPPED = "skipped"           # priority below threshold or pruned


@dataclass
class SubQuestion:
    """One node in the :class:`ResearchPlan` tree.

    Mutable on purpose: 15b mutates ``status`` / ``answer`` /
    ``answered_at`` as it executes. The planner only writes ``status``
    once, to ``PLANNED``.

    Field shape is the contract handed to 15b — DO NOT change without
    bumping the on-disk plan.json schema version (see :mod:`...plan`).
    """

    text: str
    parent_id: str | None = None
    depth: int = 0
    priority: float = 0.5
    required_sources: tuple[SourceRoute, ...] = (SourceRoute.REASONING,)
    rationale: str = ""

    children: list[SubQuestion] = field(default_factory=list)

    # Identity + lifecycle.
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: SubQuestionStatus = SubQuestionStatus.PLANNED
    answer: str | None = None
    citations: tuple[str, ...] = ()
    answered_at: str | None = None
    error: str | None = None

    # ----- helpers ------------------------------------------------------ #

    def is_root(self) -> bool:
        return self.parent_id is None

    def is_leaf(self) -> bool:
        return not self.children

    def walk(self) -> list[SubQuestion]:
        """Pre-order traversal returning self + every descendant."""
        out: list[SubQuestion] = [self]
        for child in self.children:
            out.extend(child.walk())
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "parent_id": self.parent_id,
            "depth": self.depth,
            "priority": round(float(self.priority), 4),
            "required_sources": [s.value for s in self.required_sources],
            "rationale": self.rationale,
            "status": self.status.value,
            "answer": self.answer,
            "citations": list(self.citations),
            "answered_at": self.answered_at,
            "error": self.error,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> SubQuestion:
        children_raw = raw.get("children") or ()
        children = [cls.from_dict(c) for c in children_raw if isinstance(c, Mapping)]
        sources_raw = raw.get("required_sources") or ()
        sources = tuple(SourceRoute.coerce(s) for s in sources_raw)
        if not sources:
            sources = (SourceRoute.REASONING,)
        status_raw = str(raw.get("status") or SubQuestionStatus.PLANNED.value)
        try:
            status = SubQuestionStatus(status_raw)
        except ValueError:
            status = SubQuestionStatus.PLANNED
        node = cls(
            id=str(raw.get("id") or uuid.uuid4().hex[:12]),
            text=str(raw.get("text") or ""),
            parent_id=raw.get("parent_id") if raw.get("parent_id") else None,
            depth=int(raw.get("depth") or 0),
            priority=float(raw.get("priority") or 0.5),
            required_sources=sources,
            rationale=str(raw.get("rationale") or ""),
            status=status,
            answer=raw.get("answer"),
            citations=tuple(raw.get("citations") or ()),
            answered_at=raw.get("answered_at"),
            error=raw.get("error"),
            children=children,
        )
        return node


# --------------------------------------------------------------------------- #
# Internal helper.
# --------------------------------------------------------------------------- #


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_priority(raw: Any) -> float:
    """Clamp planner-provided priorities to [0.0, 1.0]."""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))


def _coerce_required_sources(
    raw: Any, *, default: Sequence[SourceRoute] = (SourceRoute.REASONING,)
) -> tuple[SourceRoute, ...]:
    """Lenient parse for the planner's ``required_sources`` field."""
    if isinstance(raw, str):
        return (SourceRoute.coerce(raw),)
    if isinstance(raw, Sequence):
        out = tuple(dict.fromkeys(SourceRoute.coerce(s) for s in raw))
        return out or tuple(default)
    return tuple(default)
