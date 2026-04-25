"""Runner registry — one entry per system-under-test.

Each :class:`Runner` accepts a goal dict and produces
:class:`benchmarks.scoring.RunArtefacts`. Runners import their SDKs
lazily inside ``run()`` so the registry stays import-safe without
the optional deps.

Add a runner: subclass ``Runner``, register the slug in
:data:`RUNNERS`, write the harness recognises it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from benchmarks.scoring import RunArtefacts


class Runner:
    """Abstract system-under-test."""

    slug: str = "abstract"
    label: str = "Abstract Runner"

    def is_available(self) -> bool:
        """Cheap probe — `True` iff this runner can be invoked.
        The harness skips unavailable runners with a warning."""
        return True

    def run(self, goal: Mapping[str, Any]) -> RunArtefacts:        # noqa: D401
        """Execute ``goal`` and return raw artefacts."""
        raise NotImplementedError


# Lazy registry: each entry is a (slug, factory) so the runner classes
# can stay import-light. The factory receives the harness's CLI flags
# (e.g. ``--orchestra-mode native``) so multiple profiles of the same
# runner reuse one class.
RUNNERS: dict[str, Callable[[Mapping[str, Any]], Runner]] = {}


def register(slug: str) -> Callable[[Callable[[Mapping[str, Any]], Runner]], Callable[[Mapping[str, Any]], Runner]]:
    """Decorator for `RUNNERS[slug] = factory`."""

    def _decorate(factory: Callable[[Mapping[str, Any]], Runner]) -> Callable[[Mapping[str, Any]], Runner]:
        RUNNERS[slug] = factory
        return factory

    return _decorate


def build(slug: str, options: Mapping[str, Any] | None = None) -> Runner:
    if slug not in RUNNERS:
        raise KeyError(f"unknown runner: {slug!r}. Known: {sorted(RUNNERS)}")
    return RUNNERS[slug](options or {})


# Trigger registry side-effects.
from benchmarks.runners import gpt_researcher as _gpt_researcher  # noqa: F401, E402
from benchmarks.runners import orchestra as _orchestra  # noqa: F401, E402

__all__ = ["RUNNERS", "Runner", "build", "register"]
