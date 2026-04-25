/**
 * Webview ↔ extension message protocol.
 *
 * The extension `postMessage`s `Outbound`; the webview replies with
 * `Inbound`. Keep both shapes loose-typed enough to evolve without
 * webview-rebuild churn (each side ignores unknown fields).
 */

import type { RunResult, WireEvent } from "../client/types";

export type Outbound =
  | { type: "init"; mode: "local" | "remote" | "offline"; theme: "light" | "dark" }
  | { type: "progress"; eventCount: number; message: string; event?: WireEvent }
  | { type: "result"; result: RunResult }
  | { type: "log"; level: "info" | "warn" | "error"; text: string };

export type Inbound =
  | { type: "ready" }
  | { type: "open-report"; path: string | null; url: string | null }
  | { type: "cancel" };
