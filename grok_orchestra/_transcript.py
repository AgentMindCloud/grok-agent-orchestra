"""Rolling transcript compaction for the simulated runtime.

After each round, every role has an updated turn. Re-feeding the full
per-round transcript would grow unbounded across rounds, so we compact:
the latest turn per role is kept verbatim while older turns collapse to a
single-line summary of the form ``<role> [r<round>]: <key point>``.

The helpers in this module are deliberately pure — no IO, no client calls,
no global state — so the behaviour can be pinned by unit tests.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = ["RoleTurn", "compact_transcript", "summary_line"]

_DEFAULT_MAX_CHARS = 4000
_SUMMARY_KEY_LEN = 140


@dataclass(frozen=True)
class RoleTurn:
    """One role's contribution during one debate round."""

    role: str
    round: int
    content: str


def summary_line(turn: RoleTurn, max_chars: int = _SUMMARY_KEY_LEN) -> str:
    """Return the one-line summary used for older turns.

    The first non-empty line of ``turn.content`` is kept and truncated to
    ``max_chars``. Blank content collapses to ``"(no content)"``.
    """
    for line in turn.content.splitlines():
        stripped = line.strip()
        if stripped:
            key = stripped[:max_chars]
            if len(stripped) > max_chars:
                key += "…"
            return f"{turn.role} [r{turn.round}]: {key}"
    return f"{turn.role} [r{turn.round}]: (no content)"


def compact_transcript(
    turns: Sequence[RoleTurn],
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    """Compact a sequence of role turns into a transcript string.

    Strategy:

    1. Find each role's latest turn — those are retained verbatim.
    2. Every earlier turn is collapsed to :func:`summary_line`.
    3. If the assembled transcript exceeds ``max_chars``, the oldest
       summary lines are dropped first; if still too long, the retained
       verbatim turns are left-trimmed in a final safety net.

    Parameters
    ----------
    turns:
        Role turns in insertion order — the order calls were made.
    max_chars:
        Soft cap on the returned string length. Defaults to 4000.
    """
    if not turns:
        return ""

    # Index each role's last turn; this is what we keep verbatim.
    latest_index_by_role: dict[str, int] = {}
    for idx, turn in enumerate(turns):
        latest_index_by_role[turn.role] = idx

    older_lines: list[str] = []
    latest_blocks: list[str] = []

    for idx, turn in enumerate(turns):
        if idx == latest_index_by_role[turn.role]:
            latest_blocks.append(
                f"{turn.role} [r{turn.round}]:\n{turn.content.strip()}"
            )
        else:
            older_lines.append(summary_line(turn))

    parts: list[str] = []
    if older_lines:
        parts.append("\n".join(older_lines))
    parts.extend(latest_blocks)

    transcript = "\n\n".join(parts)
    if len(transcript) <= max_chars:
        return transcript

    # Drop oldest summary lines one at a time until under the cap.
    while older_lines and len(transcript) > max_chars:
        older_lines.pop(0)
        parts = []
        if older_lines:
            parts.append("\n".join(older_lines))
        parts.extend(latest_blocks)
        transcript = "\n\n".join(parts)

    if len(transcript) <= max_chars:
        return transcript

    # Last-resort left-trim of the verbatim blocks.
    return transcript[-max_chars:]
