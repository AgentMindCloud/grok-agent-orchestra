/**
 * Event narrowing helpers for the WebSocket frame stream.
 *
 * The backend emits a heterogeneous stream of events with a `type`
 * discriminator (see `grok_orchestra/web/main.py` and the runtime
 * MultiAgentEvent shape). We model them loosely as `WireEvent` and
 * give the UI typed narrowers + a per-role colour map.
 */

import type { WireEvent } from "@/types/api";

export type RoleName = "Grok" | "Harper" | "Benjamin" | "Lucas";

export type StreamKind =
  | "token"
  | "tool_call"
  | "tool_result"
  | "reasoning_tick"
  | "error"
  | "final";

export interface StreamEvent extends WireEvent {
  type: "stream";
  kind: StreamKind;
  role?: RoleName;
  text?: string;
  tool_name?: string;
  tool_args?: unknown;
  result?: unknown;
  effort?: string;
  error?: string;
}

export interface RoleStartedEvent extends WireEvent {
  type: "role_started";
  role: RoleName;
}

export interface RoleCompletedEvent extends WireEvent {
  type: "role_completed";
  role: RoleName;
  output: string;
}

export interface DebateRoundStartedEvent extends WireEvent {
  type: "debate_round_started";
  round_n: number;
}

export interface LucasPassedEvent extends WireEvent {
  type: "lucas_passed";
  confidence: number;
}

export interface LucasVetoEvent extends WireEvent {
  type: "lucas_veto";
  reason: string;
  blocked_content: string;
}

export interface RunCompletedEvent extends WireEvent {
  type: "run_completed";
  final_output: string;
  usage?: Record<string, unknown>;
}

export interface RunFailedEvent extends WireEvent {
  type: "run_failed";
  error: string;
}

export interface SnapshotBeginEvent extends WireEvent {
  type: "snapshot_begin";
  run: Record<string, unknown>;
}

export interface SnapshotEndEvent extends WireEvent {
  type: "snapshot_end";
}

export type TerminalEvent = RunCompletedEvent | RunFailedEvent;

export const TERMINAL_TYPES = new Set(["run_completed", "run_failed"]);

export function isTerminal(ev: WireEvent): ev is TerminalEvent {
  return TERMINAL_TYPES.has(ev.type);
}

export function isStream(ev: WireEvent): ev is StreamEvent {
  return ev.type === "stream";
}

export function isRoleStarted(ev: WireEvent): ev is RoleStartedEvent {
  return ev.type === "role_started";
}

export function isRoleCompleted(ev: WireEvent): ev is RoleCompletedEvent {
  return ev.type === "role_completed";
}

export function isDebateRoundStarted(
  ev: WireEvent,
): ev is DebateRoundStartedEvent {
  return ev.type === "debate_round_started";
}

export function isLucasPassed(ev: WireEvent): ev is LucasPassedEvent {
  return ev.type === "lucas_passed";
}

export function isLucasVeto(ev: WireEvent): ev is LucasVetoEvent {
  return ev.type === "lucas_veto";
}

/**
 * Per-role colour mapping. Mirrors the deep-orange Grok palette used
 * by the docs site so the dashboard reads as part of the same
 * product.
 */
export const ROLE_TONE: Record<RoleName, string> = {
  Grok: "text-role-grok border-role-grok/30 bg-role-grok/5",
  Harper: "text-role-harper border-role-harper/30 bg-role-harper/5",
  Benjamin: "text-role-benjamin border-role-benjamin/30 bg-role-benjamin/5",
  Lucas: "text-role-lucas border-role-lucas/30 bg-role-lucas/5",
};
