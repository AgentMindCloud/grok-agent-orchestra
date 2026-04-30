"""Rich-powered streaming TUI for live multi-agent debate.

:class:`DebateTUI` is a context manager that renders a 4-region Rich Layout
while native multi-agent events stream in. It degrades gracefully when the
shared console is not attached to a TTY (e.g. under CI): events are recorded
and rendered as plain structured log lines instead of a live layout.

The design is a deliberate wow-moment: monochrome cyan/white, rounded boxes,
zero flicker. All state transitions are serialised through a small lock so
``record_event`` / ``render_reasoning`` are safe to call from event callbacks
firing on whichever thread the SDK happens to use.
"""

from __future__ import annotations

import threading
from collections import deque
from types import TracebackType
from typing import ClassVar

from grok_build_bridge import _console
from rich import box
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from grok_orchestra.multi_agent_client import MultiAgentEvent

_BORDER = "cyan"
_TITLE_STYLE = "bold cyan"
_REFRESH_HZ = 12
_MAX_FOOTER_ROWS = 5
_MAX_BODY_CHARS = 4000


class DebateTUI:
    """Live TUI for Orchestra's multi-agent debate.

    Usage::

        with DebateTUI(goal="...", agent_count=4) as tui:
            for ev in client.stream_multi_agent(...):
                tui.record_event(ev)
            tui.finalize(final_text)

    When ``stdout`` is not a TTY the layout is replaced by structured log
    lines so logs in CI remain readable.

    **Re-entrant by design.** When a :class:`DebateTUI` enters its context
    while another instance is already active (e.g. the combined runtime
    opens an outer TUI and a nested simulated runtime tries to open its
    own), the inner instance becomes a transparent delegate to the outer
    one — every public method (``record_event`` / ``render_reasoning`` /
    ``start_role_turn`` / ``set_phase``) forwards to the outer TUI, and
    the inner ``__exit__`` and ``finalize`` are no-ops. This lets the
    combined runtime present one continuous show across phases.
    """

    _active: ClassVar[DebateTUI | None] = None

    def __init__(
        self,
        *,
        goal: str = "",
        agent_count: int = 4,
        console: Console | None = None,
    ) -> None:
        self.goal = goal
        self.agent_count = agent_count
        self.console: Console = console or _console.console
        self._tty = bool(getattr(self.console, "is_terminal", True))
        self._lock = threading.Lock()
        self._tokens: list[str] = []
        self._tools: deque[str] = deque(maxlen=_MAX_FOOTER_ROWS * 2)
        self._reasoning_tokens = 0
        self._event_counts: dict[str, int] = {}
        self._layout: Layout | None = None
        self._live: Live | None = None
        self._finalized = False
        self._active_role: tuple[str, str, int, str] | None = None
        self._phase: tuple[str, str] | None = None
        self._delegate: DebateTUI | None = None

    # ------------------------------------------------------------------ #
    # Context manager.
    # ------------------------------------------------------------------ #

    def __enter__(self) -> DebateTUI:
        if DebateTUI._active is not None and DebateTUI._active is not self:
            # Nested — become a transparent delegate to the outer TUI.
            self._delegate = DebateTUI._active
            return self
        if self._tty:
            self._layout = self._build_layout()
            self._refresh_all()
            self._live = Live(
                self._layout,
                console=self.console,
                refresh_per_second=_REFRESH_HZ,
                screen=False,
                transient=False,
            )
            self._live.__enter__()
        else:
            self.console.log(
                f"[bold cyan]debate start[/bold cyan] goal={self.goal!r} "
                f"agent_count={self.agent_count}"
            )
        DebateTUI._active = self
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._delegate is not None:
            # Nested context — leave the outer owner intact.
            self._delegate = None
            return
        if self._live is not None:
            self._live.__exit__(exc_type, exc, tb)
            self._live = None
        if DebateTUI._active is self:
            DebateTUI._active = None

    # ------------------------------------------------------------------ #
    # Public recording surface.
    # ------------------------------------------------------------------ #

    def record_event(self, ev: MultiAgentEvent) -> None:
        """Record a streamed :class:`MultiAgentEvent` into the layout."""
        if self._delegate is not None:
            self._delegate.record_event(ev)
            return
        with self._lock:
            self._event_counts[ev.kind] = self._event_counts.get(ev.kind, 0) + 1
            if ev.kind in ("token", "final") and ev.text:
                self._tokens.append(ev.text)
                self._trim_tokens()
                self._refresh_right()
            elif ev.kind == "reasoning_tick" and ev.reasoning_tokens:
                self._reasoning_tokens += ev.reasoning_tokens
                self._refresh_left()
            elif ev.kind == "tool_call" and ev.tool_name:
                self._tools.append(ev.tool_name)
                self._refresh_footer()
                if not self._tty:
                    self.console.log(f"[dim]tool_call: {ev.tool_name}[/dim]")
            elif ev.kind == "tool_result":
                self._refresh_footer()
            elif ev.kind == "rate_limit":
                self._tokens.append(
                    "\n[bold red]⚠ rate-limited; aborting native stream[/bold red]\n"
                )
                self._refresh_right()

    def render_reasoning(self, total_tokens: int) -> None:
        """Replace the running reasoning-token counter with ``total_tokens``."""
        if self._delegate is not None:
            self._delegate.render_reasoning(total_tokens)
            return
        with self._lock:
            self._reasoning_tokens = total_tokens
            self._refresh_left()

    def set_phase(self, label: str, color: str = "cyan") -> None:
        """Update the live header to show the currently running phase.

        Used by the combined runtime to flow the user from
        ``"🎯 Bridge: generating code"`` → ``"🎤 Orchestra: 4-agent
        debate"`` → ``"🛡 Lucas: final veto"`` inside one continuous
        Live render — no teardown / re-setup flicker.
        """
        if self._delegate is not None:
            self._delegate.set_phase(label, color)
            return
        with self._lock:
            self._phase = (label, color)
            self._refresh_header()
            if not self._tty:
                self.console.log(f"[bold {color}]{label}[/bold {color}]")

    def start_role_turn(
        self,
        role_name: str,
        role_type: str,
        round_num: int,
        color: str = "cyan",
    ) -> None:
        """Mark the start of a new named-role turn in the simulated debate.

        Renders a coloured divider into the debate pane and updates the
        header so the viewer can see who is currently speaking at a glance.

        Parameters
        ----------
        role_name:
            Display name of the role (``"Grok"``, ``"Harper"``, ...).
        role_type:
            Functional role (``"coordinator"``, ``"researcher"``, ...).
        round_num:
            Debate round number, 1-indexed.
        color:
            Rich colour name to use for the header / divider.
        """
        if self._delegate is not None:
            self._delegate.start_role_turn(role_name, role_type, round_num, color)
            return
        with self._lock:
            self._active_role = (role_name, role_type, round_num, color)
            divider = (
                f"\n\n[bold {color}]▶ {role_name} · {role_type} · r{round_num}[/bold {color}]\n"
            )
            self._tokens.append(divider)
            self._trim_tokens()
            self._refresh_header()
            self._refresh_right()
            if not self._tty:
                self.console.log(
                    f"[bold {color}]▶ {role_name}[/bold {color}] "
                    f"[dim]{role_type} · r{round_num}[/dim]"
                )

    # ------------------------------------------------------------------ #
    # Finalisation.
    # ------------------------------------------------------------------ #

    def finalize(self, summary: str | None = None) -> None:
        """Close the live layout and print a terminal summary panel.

        When this TUI is acting as a delegate for an outer one, finalize
        is a no-op — the outer owner closes the Live and prints the
        summary.
        """
        if self._delegate is not None:
            return
        if self._finalized:
            return
        self._finalized = True
        if self._live is not None:
            self._live.__exit__(None, None, None)
            self._live = None
        body = Text()
        body.append("✓ Debate complete\n", style="bold green")
        body.append(f"reasoning tokens: {self._reasoning_tokens}\n", style="white")
        counts = ", ".join(f"{k}={v}" for k, v in sorted(self._event_counts.items()))
        body.append(f"events: {counts or 'none'}\n", style="dim")
        if summary:
            body.append("\n", style="white")
            body.append(summary, style="white")
        self.console.print(
            Panel(body, box=box.ROUNDED, border_style=_BORDER, title="grok-orchestra")
        )

    # ------------------------------------------------------------------ #
    # Internal layout building.
    # ------------------------------------------------------------------ #

    def _build_layout(self) -> Layout:
        layout = Layout(name="root")
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=_MAX_FOOTER_ROWS + 2),
        )
        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=3),
        )
        return layout

    def _refresh_all(self) -> None:
        self._refresh_header()
        self._refresh_left()
        self._refresh_right()
        self._refresh_footer()

    def _refresh_header(self) -> None:
        if self._layout is None:
            return
        header = Text()
        header.append("grok-orchestra · ", style=_TITLE_STYLE)
        if self._phase is not None:
            label, color = self._phase
            header.append(label, style=f"bold {color}")
        else:
            header.append("multi-agent debate", style="white")
        if self._active_role is not None:
            role_name, role_type, round_num, color = self._active_role
            header.append("  ·  ")
            header.append(
                f"▶ {role_name}", style=f"bold {color}"
            )
            header.append(f" ({role_type}, r{round_num})", style="dim")
        if self.goal:
            header.append(f"\ngoal: {self.goal}", style="dim")
        header.append(f"\nagent_count: {self.agent_count}", style="dim")
        self._layout["header"].update(
            Panel(header, box=box.ROUNDED, border_style=_BORDER)
        )

    def _refresh_left(self) -> None:
        if self._layout is None:
            return
        gauge = Text()
        gauge.append("reasoning\n", style=_TITLE_STYLE)
        gauge.append(f"{self._reasoning_tokens}", style="bold white")
        gauge.append(" tokens", style="dim")
        self._layout["left"].update(
            Panel(
                Align.center(gauge, vertical="middle"),
                box=box.ROUNDED,
                border_style=_BORDER,
                title="effort",
            )
        )

    def _refresh_right(self) -> None:
        if self._layout is None:
            return
        body_text = "".join(self._tokens) or "[dim]…waiting for tokens…[/dim]"
        body = Text.from_markup(body_text)
        self._layout["right"].update(
            Panel(body, box=box.ROUNDED, border_style=_BORDER, title="debate")
        )

    def _refresh_footer(self) -> None:
        if self._layout is None:
            return
        table = Table.grid(padding=(0, 2))
        table.add_column(style="dim")
        table.add_column(style="white")
        rows = list(self._tools)[-_MAX_FOOTER_ROWS:] or ["(none yet)"]
        for idx, name in enumerate(rows, start=1):
            table.add_row(f"{idx:>2}", name)
        self._layout["footer"].update(
            Panel(table, box=box.ROUNDED, border_style=_BORDER, title="tool calls")
        )

    def _trim_tokens(self) -> None:
        joined_len = sum(len(t) for t in self._tokens)
        if joined_len <= _MAX_BODY_CHARS:
            return
        # Drop from the front until under the cap.
        while self._tokens and sum(len(t) for t in self._tokens) > _MAX_BODY_CHARS:
            self._tokens.pop(0)
