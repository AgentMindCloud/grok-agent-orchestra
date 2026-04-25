/**
 * Top-level webview component. Manages four chunks of state:
 *   - mode (local / remote / offline) — set by the extension's `init`.
 *   - lanes (per-role token bubbles) — derived from `progress.event`.
 *   - lucas (verdict log) — same.
 *   - result (final RunResult) — set on `result`.
 *
 * Layout mirrors the courtroom from Prompt 16b (Harper / Benjamin /
 * Grok lanes, Lucas judge bench) but at "minimal viable" fidelity —
 * the full Tailwind/shadcn surface is overkill for the inner-loop
 * use case the extension serves.
 */

import { useEffect, useMemo, useState } from "react";

import { DebateLanes, type LaneState } from "./DebateLanes";
import { FinalReport } from "./FinalReport";
import { LucasPanel, type LucasState } from "./LucasPanel";
import type { RunResult, WireEvent } from "./api";
import type { Inbound, Outbound } from "./messages";

declare const acquireVsCodeApi: () => { postMessage: (msg: Inbound) => void };
const vscode = typeof acquireVsCodeApi === "function" ? acquireVsCodeApi() : null;

export function App(): JSX.Element {
  const [mode, setMode] = useState<"local" | "remote" | "offline">("offline");
  const [events, setEvents] = useState<WireEvent[]>([]);
  const [statusLine, setStatusLine] = useState<string>("waiting…");
  const [result, setResult] = useState<RunResult | null>(null);

  useEffect(() => {
    function onMessage(ev: MessageEvent<Outbound>): void {
      const msg = ev.data;
      if (!msg || typeof msg !== "object") return;
      switch (msg.type) {
        case "init":
          setMode(msg.mode);
          setEvents([]);
          setResult(null);
          setStatusLine("ready");
          break;
        case "progress":
          setStatusLine(msg.message);
          if (msg.event) setEvents((prev) => [...prev, msg.event!]);
          break;
        case "result":
          setResult(msg.result);
          setStatusLine(
            msg.result.success
              ? `done in ${msg.result.durationSeconds.toFixed(1)}s`
              : msg.result.exitCode === 4
                ? "Lucas vetoed"
                : "failed",
          );
          break;
      }
    }
    window.addEventListener("message", onMessage);
    vscode?.postMessage({ type: "ready" });
    return () => window.removeEventListener("message", onMessage);
  }, []);

  const lanes = useMemo<LaneState>(() => buildLanes(events), [events]);
  const lucas = useMemo<LucasState>(() => buildLucas(events, result), [events, result]);

  const onOpenReport = () => {
    if (!vscode || !result) return;
    vscode.postMessage({
      type: "open-report",
      path: result.reportPath ?? null,
      url: result.reportUrl ?? null,
    });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: 16, gap: 16 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <strong>Agent Orchestra</strong>
          <span style={{ marginLeft: 8, color: "var(--vscode-descriptionForeground)" }}>
            mode: {mode} · {statusLine}
          </span>
        </div>
        {result ? (
          <button
            onClick={onOpenReport}
            style={{
              background: "var(--vscode-button-background)",
              color: "var(--vscode-button-foreground)",
              border: "none",
              padding: "6px 12px",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >
            Open report
          </button>
        ) : null}
      </header>

      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "minmax(0,1fr) 280px", gap: 12, minHeight: 0 }}>
        <DebateLanes lanes={lanes} />
        <LucasPanel state={lucas} />
      </div>

      <FinalReport result={result} />
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Reducers — same shape as the Next.js `useStreamModel` from 16b but
// half the size (no virtualisation, no framer-motion, no citation
// extraction). This is the minimal viable courtroom view.
// --------------------------------------------------------------------------- //

const ROLES = ["Harper", "Benjamin", "Grok", "Lucas"] as const;
type Role = (typeof ROLES)[number];

function buildLanes(events: WireEvent[]): LaneState {
  const lanes: LaneState = { Harper: [], Benjamin: [], Grok: [], Lucas: [] };
  const open: Partial<Record<Role, { id: string; text: string; closed: boolean; status: "ok" | "vetoed" }>> = {};
  for (const ev of events) {
    const role = (typeof ev.role === "string" ? ev.role : "") as Role;
    if (!ROLES.includes(role)) continue;
    if (ev.type === "role_started") {
      const id = `${role}-${ev.seq ?? lanes[role].length}`;
      const bubble = { id, text: "", closed: false, status: "ok" as const };
      open[role] = bubble;
      lanes[role].push(bubble);
      continue;
    }
    if (ev.type === "role_completed") {
      const ob = open[role];
      if (ob) {
        if (typeof ev.text === "string" && ev.text.length > ob.text.length) ob.text = ev.text;
        ob.closed = true;
        delete open[role];
      }
      continue;
    }
    if (ev.type === "stream" && ev.kind === "token" && typeof ev.text === "string") {
      const ob = open[role] ?? (open[role] = { id: `${role}-imp-${events.indexOf(ev)}`, text: "", closed: false, status: "ok" });
      ob.text += ev.text;
      if (!lanes[role].includes(ob)) lanes[role].push(ob);
    }
  }
  return lanes;
}

function buildLucas(events: WireEvent[], result: RunResult | null): LucasState {
  const verdicts: LucasState["verdicts"] = [];
  let confidence: number | null = null;
  let status: LucasState["status"] = "idle";
  for (const ev of events) {
    if (ev.type === "lucas_passed") {
      const c = typeof ev["confidence"] === "number" ? (ev["confidence"] as number) : undefined;
      verdicts.push({ kind: "passed", confidence: c });
      confidence = c ?? confidence;
      status = "passed";
    } else if (ev.type === "lucas_veto") {
      verdicts.push({
        kind: "vetoed",
        reason: typeof ev["reason"] === "string" ? (ev["reason"] as string) : undefined,
        blockedContent: typeof ev["blocked_content"] === "string" ? (ev["blocked_content"] as string) : undefined,
      });
      status = "vetoed";
    }
  }
  if (result?.vetoReport) {
    confidence = result.vetoReport.confidence ?? confidence;
    if (result.vetoReport.approved === false) status = "vetoed";
    else if (result.vetoReport.approved === true && status === "idle") status = "passed";
  }
  if (status === "idle" && events.length > 0) status = "observing";
  return { status, confidence, verdicts };
}
