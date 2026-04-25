"use client";

/**
 * Derives a structured stream model from the raw `WireEvent[]`. Every
 * component renders a slice of this — `RoleLane` reads `lanes[role]`,
 * `LucasPanel` reads `lucas`, `RunHeader` reads `usage` + `roundN`.
 *
 * Reducer-style folds keep this O(events) overall. The model is
 * recomputed from scratch on every event burst because the event
 * stream is monotonic and small (capped to 5000 by `useRunStream`).
 * That keeps the data path debuggable; if profiling later shows it
 * matters we can switch to incremental updates.
 */

import { useMemo } from "react";

import {
  isDebateRoundStarted,
  isLucasPassed,
  isLucasVeto,
  isRoleCompleted,
  isRoleStarted,
  isStream,
  isTerminal,
  type RoleName,
} from "@/lib/events";
import { extractCitations } from "@/lib/citations";
import { LANE_ROLES } from "@/lib/role-meta";
import type { WireEvent } from "@/types/api";

// --------------------------------------------------------------------------- #
// Per-message + per-lane shapes.
// --------------------------------------------------------------------------- #

export type MessageStatus = "streaming" | "done" | "vetoed";

export interface ToolCall {
  id: string;
  toolName: string;
  args: unknown;
  result?: string;
  status: "calling" | "ok" | "error";
}

export interface RoleMessage {
  id: string;
  role: RoleName;
  text: string;
  citationCount: number;
  status: MessageStatus;
  startedAt: number;             // monotonic counter (event seq) for ordering
  toolCalls: ToolCall[];
}

export interface RoleLaneModel {
  role: RoleName;
  messages: RoleMessage[];
  // The ID currently streaming (no `role_completed` yet) for the
  // streaming caret. `null` when no message is open.
  openMessageId: string | null;
  totalCitations: number;
}

// --------------------------------------------------------------------------- #
// Lucas panel state.
// --------------------------------------------------------------------------- #

export type LucasStatus =
  | "idle"            // no Lucas activity yet
  | "observing"       // run is in progress, no veto event
  | "passed"          // most recent verdict was a pass
  | "vetoed";         // most recent verdict was a veto

export interface LucasVerdict {
  id: string;
  kind: "passed" | "vetoed";
  confidence?: number;
  reason?: string;
  blockedContent?: string;
  ts: number;
}

export interface LucasState {
  status: LucasStatus;
  confidence: number | null;
  verdicts: LucasVerdict[];
  /** Set of message ids that Lucas has vetoed (used to highlight in lanes). */
  vetoedMessageIds: Set<string>;
}

// --------------------------------------------------------------------------- #
// Top-level model.
// --------------------------------------------------------------------------- #

export interface StreamModel {
  lanes: Record<RoleName, RoleLaneModel>;
  lucas: LucasState;
  /** Current debate round (1-based). 0 if no round event has fired. */
  round: number;
  /** Set when the run has terminated successfully. */
  finalOutput: string | null;
  /** Set when the run failed. */
  failureReason: string | null;
}

const EMPTY_LANES: Record<RoleName, RoleLaneModel> = {
  Grok: { role: "Grok", messages: [], openMessageId: null, totalCitations: 0 },
  Harper: { role: "Harper", messages: [], openMessageId: null, totalCitations: 0 },
  Benjamin: {
    role: "Benjamin",
    messages: [],
    openMessageId: null,
    totalCitations: 0,
  },
  Lucas: { role: "Lucas", messages: [], openMessageId: null, totalCitations: 0 },
};

// --------------------------------------------------------------------------- #
// Reducer.
// --------------------------------------------------------------------------- #

function freshLanes(): Record<RoleName, RoleLaneModel> {
  return {
    Grok: { ...EMPTY_LANES.Grok, messages: [] },
    Harper: { ...EMPTY_LANES.Harper, messages: [] },
    Benjamin: { ...EMPTY_LANES.Benjamin, messages: [] },
    Lucas: { ...EMPTY_LANES.Lucas, messages: [] },
  };
}

function nextMessageId(lane: RoleLaneModel, seq?: number): string {
  return `${lane.role}-${seq ?? lane.messages.length}-${Math.random().toString(36).slice(2, 8)}`;
}

function recomputeLaneCitationTotal(lane: RoleLaneModel): void {
  lane.totalCitations = lane.messages.reduce((sum, m) => sum + m.citationCount, 0);
}

function findOpenMessage(lane: RoleLaneModel): RoleMessage | undefined {
  if (!lane.openMessageId) return undefined;
  return lane.messages.find((m) => m.id === lane.openMessageId);
}

function buildModel(events: WireEvent[]): StreamModel {
  const lanes = freshLanes();
  const lucas: LucasState = {
    status: "idle",
    confidence: null,
    verdicts: [],
    vetoedMessageIds: new Set(),
  };
  let round = 0;
  let finalOutput: string | null = null;
  let failureReason: string | null = null;

  // Track the most-recent open message per role so vetoes can find a
  // target to highlight even when the event arrives after the message
  // closed.
  const lastClosedByRole: Partial<Record<RoleName, string>> = {};

  for (let i = 0; i < events.length; i++) {
    const ev = events[i];

    if (isDebateRoundStarted(ev)) {
      round = Math.max(round, ev.round_n);
      continue;
    }

    if (isRoleStarted(ev)) {
      const lane = lanes[ev.role];
      const id = nextMessageId(lane, ev.seq);
      lane.messages.push({
        id,
        role: ev.role,
        text: "",
        citationCount: 0,
        status: "streaming",
        startedAt: ev.seq ?? i,
        toolCalls: [],
      });
      lane.openMessageId = id;
      continue;
    }

    if (isRoleCompleted(ev)) {
      const lane = lanes[ev.role];
      const open = findOpenMessage(lane);
      if (open) {
        // Prefer the longer of the streamed buffer vs the final
        // payload — the runtime sometimes only emits the full text
        // on `role_completed` (no token stream).
        if (ev.output && ev.output.length > open.text.length) {
          open.text = ev.output;
        }
        open.status = "done";
        open.citationCount = extractCitations(open.text).length;
        recomputeLaneCitationTotal(lane);
        lastClosedByRole[ev.role] = open.id;
      }
      lane.openMessageId = null;
      continue;
    }

    if (isStream(ev)) {
      const role = ev.role;
      if (!role) continue;
      const lane = lanes[role];
      if (ev.kind === "token" && ev.text) {
        let open = findOpenMessage(lane);
        if (!open) {
          // Implicit start — the runtime emitted tokens without a
          // matching role_started. Open a synthetic message so the
          // text isn't dropped on the floor.
          const id = nextMessageId(lane, ev.seq);
          open = {
            id,
            role,
            text: "",
            citationCount: 0,
            status: "streaming",
            startedAt: ev.seq ?? i,
            toolCalls: [],
          };
          lane.messages.push(open);
          lane.openMessageId = id;
        }
        open.text += ev.text;
        continue;
      }
      if (ev.kind === "tool_call" && ev.tool_name) {
        const open = findOpenMessage(lane);
        if (open) {
          open.toolCalls.push({
            id: `tc-${ev.seq ?? i}`,
            toolName: ev.tool_name,
            args: ev.tool_args,
            status: "calling",
          });
        }
        continue;
      }
      if (ev.kind === "tool_result" && ev.tool_name) {
        const open = findOpenMessage(lane);
        if (open) {
          // Reverse-search so a re-used tool name attaches to the
          // most-recent call.
          for (let j = open.toolCalls.length - 1; j >= 0; j--) {
            if (open.toolCalls[j].toolName === ev.tool_name) {
              open.toolCalls[j].status = "ok";
              open.toolCalls[j].result =
                typeof ev.result === "string"
                  ? ev.result
                  : JSON.stringify(ev.result, null, 2);
              break;
            }
          }
        }
        continue;
      }
      if (ev.kind === "error" && ev.error) {
        const open = findOpenMessage(lane);
        if (open) open.status = "done";
        continue;
      }
      continue;
    }

    if (isLucasPassed(ev)) {
      lucas.status = "passed";
      lucas.confidence = ev.confidence;
      lucas.verdicts.push({
        id: `lp-${ev.seq ?? i}`,
        kind: "passed",
        confidence: ev.confidence,
        ts: ev.seq ?? i,
      });
      continue;
    }

    if (isLucasVeto(ev)) {
      lucas.status = "vetoed";
      lucas.verdicts.push({
        id: `lv-${ev.seq ?? i}`,
        kind: "vetoed",
        reason: ev.reason,
        blockedContent: ev.blocked_content,
        ts: ev.seq ?? i,
      });
      // Highlight the most recently-closed message in any of the
      // non-Lucas lanes, since those are the candidates for the
      // blocked content.
      for (const role of LANE_ROLES) {
        const id = lastClosedByRole[role];
        if (id) {
          lucas.vetoedMessageIds.add(id);
          const lane = lanes[role];
          const m = lane.messages.find((x) => x.id === id);
          if (m) m.status = "vetoed";
        }
      }
      continue;
    }

    if (isTerminal(ev)) {
      if (ev.type === "run_completed") {
        finalOutput =
          typeof ev.final_output === "string" ? ev.final_output : null;
        if (lucas.status === "idle") lucas.status = "passed";
      } else {
        failureReason =
          typeof ev.error === "string" ? ev.error : "run failed";
      }
      continue;
    }
  }

  if (lucas.status === "idle" && events.length > 0) lucas.status = "observing";

  return { lanes, lucas, round, finalOutput, failureReason };
}

export function useStreamModel(events: WireEvent[]): StreamModel {
  return useMemo(() => buildModel(events), [events]);
}

// Exported for unit tests — the reducer is the interesting bit.
export { buildModel };
