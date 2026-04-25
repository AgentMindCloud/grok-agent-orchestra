#!/usr/bin/env python3
"""Run an Agent Orchestra orchestration against a remote FastAPI backend.

Used directly by the SKILL when ``--force-remote`` is passed, and
delegated-to by ``run_orchestration.py`` when the local CLI isn't
installed but ``AGENT_ORCHESTRA_REMOTE_URL`` is set.

Talks to the canonical web API surface (``grok_orchestra/web/main.py``):

  POST /api/run                        → {run_id}
  GET  /api/runs/{run_id}              → status + final_content
  GET  /api/runs/{run_id}/report.md    → text/markdown report

Authentication: when the backend has ``GROK_ORCHESTRA_AUTH_PASSWORD``
set, ``/api/run`` is gated. Pass the same value via the
``AGENT_ORCHESTRA_REMOTE_TOKEN`` env var; this script sends it as
``Authorization: Bearer <token>`` on every request.

Stdlib-only — no ``httpx`` / ``requests`` dependency. Keeps the skill
installable in any Claude environment without extra pip work.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Exit codes line up with run_orchestration.py and grok-orchestra CLI.
EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_RUNTIME = 3
EXIT_VETOED = 4
EXIT_NETWORK = 6


def _truncate_for_preview(text: str, max_bytes: int = 8192) -> str:
    """Trim ``text`` to ``max_bytes`` UTF-8 bytes preserving the head + tail.

    Operates on bytes, not characters, so non-ASCII content can't blow
    the budget. Never splits an inline image link
    ``![alt](path)`` mid-bracket — backs up to the previous newline if
    the cut would land inside one.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    head_budget = int(max_bytes * 0.75)
    tail_budget = max_bytes - head_budget - 64  # leave room for the marker

    head = encoded[:head_budget].decode("utf-8", errors="ignore")
    if "![" in head[-200:] and head.rfind("\n") > 0:
        head = head[: head.rfind("\n")]
    tail = encoded[-tail_budget:].decode("utf-8", errors="ignore")
    if "![" in tail[:200] and tail.find("\n") > 0:
        tail = tail[tail.find("\n") + 1 :]
    return f"{head}\n\n…(truncated; {len(encoded)} bytes total)…\n\n{tail}"


def _request(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any] | str]:
    """Tiny urllib wrapper. Returns ``(status, parsed-or-raw-text)``."""
    headers: dict[str, str] = {"Accept": "application/json"}
    data: bytes | None = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url=url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            text = raw.decode("utf-8", errors="replace")
            if "application/json" in ctype:
                try:
                    return resp.status, json.loads(text)
                except json.JSONDecodeError:
                    return resp.status, text
            return resp.status, text
    except urllib.error.HTTPError as exc:
        body_raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body_raw)
        except json.JSONDecodeError:
            return exc.code, body_raw


def _emit_progress(line: str) -> None:
    """Single point where progress lines go to stderr.

    Claude Code's Bash tool returns final stdout — but human callers
    debugging the script directly want live progress. Stderr is the
    universal fit.
    """
    print(line, file=sys.stderr, flush=True)


def _resolve_yaml(template: str | None, yaml_path: str | None) -> tuple[str, str | None]:
    """Return ``(yaml_text, template_name)`` for the run body.

    ``--template <slug>`` is the common path: send an empty YAML and
    let the backend resolve the slug via ``RunBody.template_name`` →
    canonical template lookup. ``--yaml <path>`` is the explicit-spec
    escape hatch.
    """
    if yaml_path:
        body = Path(yaml_path).read_text(encoding="utf-8")
        return body, None
    if not template:
        raise ValueError("must pass --template <slug> or --yaml <path>")
    return f"# Resolved server-side from template_name: {template}\n", template


def _poll_until_done(
    base: str,
    run_id: str,
    *,
    token: str | None,
    poll_interval: float,
    timeout: float,
) -> dict[str, Any]:
    """Poll ``GET /api/runs/{run_id}`` until status leaves
    ``{pending, running}`` or ``timeout`` elapses."""
    started = time.monotonic()
    last_event_count = 0
    while True:
        elapsed = time.monotonic() - started
        if elapsed > timeout:
            raise TimeoutError(f"run {run_id} did not finish in {timeout:.0f}s")

        status, payload = _request(
            "GET", f"{base}/api/runs/{run_id}", token=token, timeout=15.0
        )
        if status >= 500 or not isinstance(payload, dict):
            raise RuntimeError(f"GET /api/runs/{run_id} → {status}: {payload}")
        if status == 404:
            raise RuntimeError(f"run {run_id} disappeared from the registry")

        run_status = str(payload.get("status") or "running")
        events = payload.get("events") or []
        new_event_count = len(events)
        if new_event_count > last_event_count:
            last = events[-1] if isinstance(events, list) and events else {}
            kind = (last or {}).get("type") or (last or {}).get("kind") or "event"
            role = (last or {}).get("role")
            tag = f"role={role} " if role else ""
            _emit_progress(
                f"[{int(elapsed):3d}s] events={new_event_count} {tag}last={kind}"
            )
            last_event_count = new_event_count

        if run_status not in {"pending", "running"}:
            return payload
        time.sleep(poll_interval)


def _fetch_report(base: str, run_id: str, *, token: str | None) -> str:
    """Fetch the rendered Markdown report. Empty string on 404
    (e.g. ``--dry-run`` flows where Publisher isn't invoked)."""
    status, payload = _request(
        "GET", f"{base}/api/runs/{run_id}/report.md", token=token, timeout=30.0
    )
    if status == 200 and isinstance(payload, str):
        return payload
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    spec = parser.add_mutually_exclusive_group(required=True)
    spec.add_argument("--template", help="Bundled template slug.")
    spec.add_argument("--yaml", dest="yaml_path", help="Path to a YAML spec.")
    parser.add_argument(
        "--inputs-json", default="{}",
        help="JSON object passed as RunBody.inputs (default '{}').",
    )
    parser.add_argument(
        "--simulated", action="store_true",
        help="Force simulated mode regardless of what the YAML resolves to.",
    )
    parser.add_argument("--poll-interval", type=float, default=3.0)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument(
        "--base-url", default=None,
        help="Override AGENT_ORCHESTRA_REMOTE_URL.",
    )
    args = parser.parse_args(argv)

    base = (args.base_url or os.environ.get("AGENT_ORCHESTRA_REMOTE_URL") or "").rstrip("/")
    if not base:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "AGENT_ORCHESTRA_REMOTE_URL is not set",
                }
            )
        )
        return EXIT_CONFIG

    token = os.environ.get("AGENT_ORCHESTRA_REMOTE_TOKEN") or None
    try:
        inputs = json.loads(args.inputs_json or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"--inputs-json invalid: {exc}"}))
        return EXIT_CONFIG
    try:
        yaml_text, template_name = _resolve_yaml(args.template, args.yaml_path)
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return EXIT_CONFIG

    started = time.monotonic()
    body = {
        "yaml": yaml_text,
        "inputs": inputs,
        "simulated": bool(args.simulated),
        "template_name": template_name,
    }
    try:
        status, payload = _request(
            "POST", f"{base}/api/run", body=body, token=token, timeout=30.0
        )
    except urllib.error.URLError as exc:
        print(json.dumps({"ok": False, "error": f"network error reaching {base}: {exc}"}))
        return EXIT_NETWORK

    if status == 401:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "401 unauthorized — set AGENT_ORCHESTRA_REMOTE_TOKEN to the backend's GROK_ORCHESTRA_AUTH_PASSWORD",
                }
            )
        )
        return EXIT_CONFIG
    if status >= 400 or not isinstance(payload, dict):
        print(json.dumps({"ok": False, "error": f"POST /api/run → {status}: {payload}"}))
        return EXIT_RUNTIME
    run_id = payload.get("run_id")
    if not run_id:
        print(json.dumps({"ok": False, "error": "POST /api/run returned no run_id"}))
        return EXIT_RUNTIME

    _emit_progress(f"[  0s] POST /api/run → {run_id}")

    try:
        final = _poll_until_done(
            base, str(run_id),
            token=token,
            poll_interval=max(0.5, args.poll_interval),
            timeout=max(10.0, args.timeout),
        )
    except (TimeoutError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "run_id": run_id, "error": str(exc)}))
        return EXIT_RUNTIME

    duration = round(time.monotonic() - started, 3)
    run_status = str(final.get("status") or "unknown")
    final_content = str(final.get("final_content") or "")
    veto = final.get("veto_report") or None

    # Lucas-veto = blocked output. Map to canonical exit 4 so callers
    # can distinguish "model failed" from "policy refused".
    veto_blocked = bool(veto and veto.get("approved") is False)

    report_md = _fetch_report(base, str(run_id), token=token) or final_content
    preview = _truncate_for_preview(report_md or final_content)

    result = {
        "ok": run_status == "completed" and not veto_blocked,
        "success": run_status == "completed" and not veto_blocked,
        "mode": "remote",
        "slug": template_name,
        "run_id": run_id,
        "status": run_status,
        "duration_seconds": duration,
        "report_url": f"{base}/api/runs/{run_id}/report.md",
        "final_content_preview": preview,
        "veto_report": veto,
        "exit_code": EXIT_VETOED
        if veto_blocked
        else (EXIT_OK if run_status == "completed" else EXIT_RUNTIME),
    }
    print(f"RESULT_JSON: {json.dumps(result)}")
    return result["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
