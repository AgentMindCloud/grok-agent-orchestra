/**
 * Re-export of the protocol shapes for the webview bundle. Kept
 * separate from the extension-side `src/util/messages.ts` so the
 * webview tsconfig (DOM lib) doesn't pull in node types via that
 * module's transitive imports.
 */

import type { ProgressUpdate, RunResult, WireEvent } from "./api";

export type Outbound =
  | { type: "init"; mode: "local" | "remote" | "offline"; theme: "light" | "dark" }
  | { type: "progress"; eventCount: number; message: string; event?: WireEvent }
  | { type: "result"; result: RunResult }
  | { type: "log"; level: "info" | "warn" | "error"; text: string };

export type Inbound =
  | { type: "ready" }
  | { type: "open-report"; path: string | null; url: string | null }
  | { type: "cancel" };

export type { ProgressUpdate };
