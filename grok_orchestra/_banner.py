"""Branded banner for the ``grok-orchestra`` CLI.

Orchestra's accent colour is violet — the deliberate contrast against
Bridge's cyan so operators can tell the two CLIs apart at a glance when
they share a terminal. The banner renders a 6-line ASCII title in a
cyan-to-violet gradient followed by a single-line tagline.

The module is side-effect-free: rendering happens only via
:func:`render_banner`. Tests can import freely.
"""

from __future__ import annotations

from collections.abc import Sequence

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

__all__ = ["GRADIENT", "TAGLINE", "render_banner"]


# Six-line ASCII title — "GROK AGENT ORCHESTRA" stacked. Kept intentionally
# compact (69 chars wide) so it fits a standard 80-column terminal.
_BANNER_LINES: Sequence[str] = (
    r"   ____            _        ___           _               _             ",
    r"  / ___| _ __ ___ | | __   / _ \ _ __ ___| |__   ___  ___| |_ _ __ __ _ ",
    r" | |  _ | '__/ _ \| |/ /  | | | | '__/ __| '_ \ / _ \/ __| __| '__/ _` |",
    r" | |_| || | | (_) |   <   | |_| | | | (__| | | |  __/\__ \ |_| | | (_| |",
    r"  \____||_|  \___/|_|\_\   \___/|_|  \___|_| |_|\___||___/\__|_|  \__,_|",
    r"                         ▸ agent · orchestra ◂                          ",
)

# Cyan → violet gradient, six stops. The hex codes step through the HSL
# arc from Bridge's cyan (#00FFFF) toward Orchestra's violet (#8B5CF6).
GRADIENT: Sequence[str] = (
    "#00FFFF",
    "#5EE1FF",
    "#9EC2FF",
    "#B69EFE",
    "#A078F6",
    "#8B5CF6",
)

TAGLINE = "4 minds. 1 safer post. Zero compromise."


def render_banner(
    console: Console,
    *,
    no_color: bool = False,
) -> None:
    """Render the branded banner + tagline to ``console``.

    Parameters
    ----------
    console:
        The Rich :class:`Console` to print into. Usually
        ``grok_build_bridge._console.console``.
    no_color:
        When true, renders the banner without the gradient so log files
        and ``--no-color`` runs stay legible.
    """
    if no_color:
        body: list[Text] = [Text(line, style="bold") for line in _BANNER_LINES]
    else:
        body = []
        for line, colour in zip(_BANNER_LINES, GRADIENT, strict=False):
            body.append(Text(line, style=f"bold {colour}"))

    tagline_style = "italic" if no_color else "italic bold #B69EFE"
    border_style = "white" if no_color else "#8B5CF6"

    renderable = Group(
        *body,
        Text(""),
        Align.center(Text(TAGLINE, style=tagline_style)),
    )
    console.print(
        Panel(
            renderable,
            box=box.ROUNDED,
            border_style=border_style,
            padding=(1, 2),
        )
    )
