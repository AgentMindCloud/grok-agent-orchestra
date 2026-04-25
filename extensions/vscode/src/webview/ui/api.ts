/**
 * Webview-side mirror of `src/client/types.ts`. Kept in this file so
 * the webview bundle never imports from outside `src/webview/ui/`
 * (which would drag node-only types into the browser tsconfig).
 */

export type RunMode = "local" | "remote";

export interface VetoReport {
  approved: boolean;
  confidence?: number;
  reasons?: string[];
}

export interface RunResult {
  ok: boolean;
  success: boolean;
  mode: RunMode;
  slug?: string | null;
  spec?: string | null;
  runId: string | null;
  status: "pending" | "running" | "completed" | "failed";
  durationSeconds: number;
  reportPath?: string | null;
  reportUrl?: string | null;
  finalContent: string;
  vetoReport: VetoReport | null;
  exitCode: number;
  errorMessage?: string;
}

export interface WireEvent {
  type: string;
  seq?: number;
  ts?: string;
  role?: string;
  text?: string;
  kind?: string;
  [key: string]: unknown;
}

export interface ProgressUpdate {
  eventCount: number;
  message: string;
  event?: WireEvent;
}
