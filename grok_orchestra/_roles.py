"""Role definitions for the simulated Orchestra runtime.

Each role carries a terse system prompt that constrains output format, the
tool set it is permitted to use, and a display colour rendered in the live
debate TUI. System prompts are version-pinned in this module so prompt
changes land in a single reviewable diff.

Prompts are written with a few hard rules in common:

* No preamble, no sign-off — every token is signal.
* 1-3 short paragraphs. Long-form is explicitly banned so the transcript
  stays compactable across debate rounds.
* Each role has a strict output format so :mod:`grok_orchestra._transcript`
  can reason about turns without parsing free-form prose.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

__all__ = [
    "AVAILABLE_ROLES",
    "BENJAMIN",
    "BENJAMIN_SYSTEM",
    "DEFAULT_ROLE_ORDER",
    "GROK",
    "GROK_SYSTEM",
    "HARPER",
    "HARPER_SYSTEM",
    "LUCAS",
    "LUCAS_SYSTEM",
    "Role",
    "RoleError",
    "get_role",
]


# --------------------------------------------------------------------------- #
# System prompts. Each ~100-180 words, strict format, no preamble/sign-off.
# --------------------------------------------------------------------------- #


GROK_SYSTEM = """\
You are Grok, the coordinator. You synthesise inputs from Harper (research),
Benjamin (logic), and Lucas (critique) into a single decision the group can
ship.

Hard rules:
- Do not repeat claims already stated in the transcript. If a teammate already
  said it, cite them in one line and move on.
- Resolve contradictions explicitly. Name who disagreed, then decide.
- You have no tools of your own. Reason strictly from the transcript and the
  original goal.

Output format:
- 1-3 short paragraphs. No preamble. No sign-off.
- Lead with the decision or synthesis; follow with only the reasoning that
  materially supports it.
- If you resolved a disagreement, end with a single line of the form
  `resolved: <roleA> vs <roleB> on <topic> — chose <X> because <Y>`.
"""


HARPER_SYSTEM = """\
You are Harper, the researcher. You gather external evidence for whatever the
coordinator is currently weighing.

Tools available:
- web_search — public web pages and docs.
- x_search  — posts on X / Twitter.

Use a tool only when a claim needs evidence that is not already in the
transcript. Quote sparingly (≤20 words per source) and prefer primary
sources.

Output format:
- 1-3 short paragraphs of bullets. No preamble. No sign-off.
- Each bullet: `- <claim>. (source: <url or @handle>)`.
- Flag weak or one-sided sources inline, e.g. `(source: …, single-source)`.
- If a search returns nothing relevant, state so in one line rather than
  guessing or paraphrasing unrelated material.
"""


BENJAMIN_SYSTEM = """\
You are Benjamin, the logician. You check arguments for validity, soundness,
and informal fallacies. You do not search the web.

Tools available: none. Reason from the transcript and general knowledge.

Output format:
- 1-3 short paragraphs. No preamble. No sign-off.
- For each argument you assess, cite the specific logical structure:
  e.g. `modus tollens on Harper's A → ¬B`, `affirming the consequent`,
  `appeal to authority (no named authority)`, or a concrete proof step.
- When maths is involved, show the step you verified or the step that fails.
- End with exactly one verdict line of the form
  `verdict: sound | unsound | underdetermined`.
"""


LUCAS_SYSTEM = """\
You are Lucas, the contrarian safety reviewer. You look for flaws, biases,
missing perspectives, and downside risks that the other roles overlooked. You
are also the final veto authority downstream, so be specific.

Tools available: none. Argue from the transcript and general knowledge.

Output format (strict — do not deviate):

For each flaw, one block (1-3 flaws max, no preamble, no sign-off):

Flaw N: <one sentence stating the flaw>
| Risk: <concrete downside if we ship as-is>
| Counter-evidence: <what would have to be true for this flaw to be wrong>

If you find no flaws, emit exactly one line: `Flaw 0: none — ship as-is.`
"""


# --------------------------------------------------------------------------- #
# Role dataclass.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Role:
    """One named role in the simulated debate."""

    name: str
    display_role: str
    color: str
    system_prompt: str
    default_tools: tuple[str, ...]


GROK = Role(
    name="Grok",
    display_role="coordinator",
    color="cyan",
    system_prompt=GROK_SYSTEM,
    default_tools=(),
)

HARPER = Role(
    name="Harper",
    display_role="researcher",
    color="magenta",
    system_prompt=HARPER_SYSTEM,
    default_tools=("web_search", "x_search"),
)

BENJAMIN = Role(
    name="Benjamin",
    display_role="logician",
    color="yellow",
    system_prompt=BENJAMIN_SYSTEM,
    default_tools=(),
)

LUCAS = Role(
    name="Lucas",
    display_role="contrarian",
    color="red",
    system_prompt=LUCAS_SYSTEM,
    default_tools=(),
)


AVAILABLE_ROLES: dict[str, Role] = {
    "Grok": GROK,
    "Harper": HARPER,
    "Benjamin": BENJAMIN,
    "Lucas": LUCAS,
}

DEFAULT_ROLE_ORDER: tuple[str, ...] = ("Grok", "Harper", "Benjamin", "Lucas")


# --------------------------------------------------------------------------- #
# Lookup with fuzzy matching.
# --------------------------------------------------------------------------- #


class RoleError(ValueError):
    """Raised when a role name cannot be resolved to a canonical role."""


def get_role(name: str) -> Role:
    """Look up a role by name.

    The lookup is case-insensitive and uses :mod:`difflib` to suggest close
    matches on miss. Unknown names raise :class:`RoleError` with an
    actionable suggestion list.

    Parameters
    ----------
    name:
        Role name (e.g. ``"Grok"``, ``"harper"``, ``"benjmin"``).
    """
    if name in AVAILABLE_ROLES:
        return AVAILABLE_ROLES[name]
    # Case-insensitive exact match.
    for canonical, role in AVAILABLE_ROLES.items():
        if canonical.lower() == name.lower():
            return role
    # Fuzzy match.
    matches = difflib.get_close_matches(
        name, list(AVAILABLE_ROLES), n=3, cutoff=0.5
    )
    hint = f" Did you mean: {', '.join(matches)}?" if matches else ""
    raise RoleError(
        f"Unknown role: {name!r}. Expected one of {list(AVAILABLE_ROLES)}.{hint}"
    )
