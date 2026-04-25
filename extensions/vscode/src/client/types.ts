/**
 * Shared shapes between the local-CLI and remote-HTTP clients.
 *
 * The same wire contract powers the Claude Skill's `remote_run.py`
 * (Prompt 17) — keep `RunResult` aligned so Prompt 19's benchmark
 * harness can consume both transparently.
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

/** WebSocket frame envelope. The backend's `/ws/runs/{run_id}` emits
 * a snapshot replay then live events; the webview cares about the
 * `type` discriminator (token / role_started / role_completed /
 * lucas_passed / lucas_veto / run_completed / run_failed). */
export interface WireEvent {
  type: string;
  seq?: number;
  ts?: string;
  role?: string;
  text?: string;
  kind?: string;
  // Free-form: the client doesn't need to model every field here;
  // the webview narrows on `type` / `kind` at render time.
  [key: string]: unknown;
}

export interface ProgressUpdate {
  /** Monotonic event count across the run so the UI can render
   * progress without re-deriving from the buffer. */
  eventCount: number;
  /** Human-readable single-line status — shown in the status bar. */
  message: string;
  /** Emitted directly by the runner (LLM tokens, lucas verdicts). */
  event?: WireEvent;
}

export type ProgressHandler = (update: ProgressUpdate) => void;

export interface RunOptions {
  /** Either a bundled template slug OR an absolute YAML file path. */
  template?: string;
  yamlPath?: string;
  yamlText?: string;
  inputs?: Record<string, unknown>;
  simulated: boolean;
  dryRun: boolean;
  /** Hard-cap the run wall time. Defaults to 15 minutes. */
  timeoutMs?: number;
  /** Forwarded to the LLM; ignored in local-CLI mode. */
  bearerToken?: string;
  /** Where the local CLI writes report.md / run.json. */
  workspacePath?: string;
  onProgress?: ProgressHandler;
  /** Cooperative cancellation. The client polls this between
   * iterations. */
  signal?: AbortSignal;
}

/** The minimal client surface every transport implements.
 *
 * Both transports also expose `reportUri()` so the
 * `viewLastReport` command can open the report regardless of
 * which mode produced it. */
export interface OrchestrationClient {
  readonly mode: RunMode;
  isAvailable(): Promise<boolean>;
  run(options: RunOptions): Promise<RunResult>;
}

export interface TemplateSummary {
  slug: string;
  name: string;
  description?: string;
  categories?: string[];
  estimatedTokens?: number;
  mode?: string;
  pattern?: string;
}
