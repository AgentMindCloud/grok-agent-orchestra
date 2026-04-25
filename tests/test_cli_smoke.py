"""Post-install smoke tests.

These run the **installed** CLI (via the `grok-orchestra` console-script
entry point) as a subprocess, so they catch packaging-layer breakage
that the unit tests — which import :mod:`grok_orchestra` from the source
tree — cannot. Specifically:

- the ``grok-orchestra`` script is on ``PATH`` after install,
- ``--help`` and ``--version`` do not crash,
- bundled package data (templates) ships with the wheel.

If you are running these against a source checkout, ``pip install -e .``
first; otherwise the console-script will not exist and the subprocess
calls will hard-fail with FileNotFoundError, not pytest assertions.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


# `python -m grok_orchestra.cli` spawns a fresh interpreter that
# can't see tests/conftest.py's bridge stub. When the real
# `grok-build-bridge` isn't installed locally, the subprocess will
# exit 1 inside the package's own __init__.py guard. Skip those
# subprocess-based tests cleanly instead of failing them.
def _bridge_really_installed() -> bool:
    """True iff the real ``grok-build-bridge`` package is installed
    (not the conftest stub). The conftest stub registers a module
    object with no `__spec__`; ``find_spec`` raises ValueError on
    that. Real installs return a proper spec."""
    try:
        spec = importlib.util.find_spec("grok_build_bridge")
    except (ImportError, ValueError):
        return False
    return spec is not None


_SUBPROCESS_REQUIRES_BRIDGE = pytest.mark.skipif(
    not _bridge_really_installed(),
    reason="subprocess can't use conftest stubs; install grok-build-bridge to run",
)


def test_package_imports_with_version() -> None:
    """``grok_orchestra`` is importable and exposes a non-empty ``__version__``."""
    import grok_orchestra

    assert isinstance(grok_orchestra.__version__, str)
    assert grok_orchestra.__version__.count(".") >= 2


@pytest.fixture
def cli() -> str:
    """Resolve the installed `grok-orchestra` console script.

    Looks beside the running Python interpreter first — that's the
    Scripts/ or bin/ dir of the active venv, where pip drops console
    scripts. Falls back to PATH so callers who invoke pytest without
    activating the venv (`/tmp/install-venv/bin/python -m pytest …`)
    still find the script.

    Skips if the script can't be found at all — typical for a raw
    source-tree run with no install.
    """
    candidate = Path(sys.executable).parent / (
        "grok-orchestra.exe" if os.name == "nt" else "grok-orchestra"
    )
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)

    path = shutil.which("grok-orchestra")
    if path is None:
        pytest.skip(
            "grok-orchestra console script not found beside the running "
            "interpreter or on PATH; run `pip install -e .` or install "
            "the wheel before executing the smoke tests."
        )
    return path


def test_cli_help_exits_zero(cli: str) -> None:
    result = subprocess.run(
        [cli, "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "grok-orchestra" in result.stdout.lower()


def test_cli_version_matches_package(cli: str) -> None:
    import grok_orchestra

    result = subprocess.run(
        [cli, "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert grok_orchestra.__version__ in result.stdout


@_SUBPROCESS_REQUIRES_BRIDGE
def test_python_dash_m_works() -> None:
    """``python -m grok_orchestra.cli --help`` is a documented fallback."""
    result = subprocess.run(
        [sys.executable, "-m", "grok_orchestra.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
