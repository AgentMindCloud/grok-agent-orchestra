/**
 * Remote-HTTP transport — talks to the Agent Orchestra FastAPI.
 *
 * Mirrors the wire contract of `skills/agent-orchestra/scripts/remote_run.py`
 * (Prompt 17). When Prompt 19's benchmark harness lands, both
 * transports will share this exact RESULT_JSON shape.
 *
 * Endpoints used:
 *   POST /api/run                         → {run_id}
 *   GET  /api/runs/{id}                   → status + events
 *   GET  /api/runs/{id}/report.md         → text/markdown
 *   GET  /api/health                      → availability probe
 *
 * Auth: bearer token sent on every request when configured.
 */

import type {
  OrchestrationClient,
  ProgressHandler,
  RunOptions,
  RunResult,
  TemplateSummary,
  WireEvent,
} from "./types";

const POLL_INTERVAL_MS = 2_000;
const DEFAULT_TIMEOUT_MS = 15 * 60 * 1_000;

interface ServerRunDetail {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  events?: WireEvent[];
  final_content?: string;
  veto_report?: { approved: boolean; confidence?: number; reasons?: string[] } | null;
}

export class RemoteClient implements OrchestrationClient {
  public readonly mode = "remote" as const;

  constructor(
    public readonly baseUrl: string,
    private readonly bearerToken?: string,
  ) {}

  /** Cheap HEAD-equivalent: GET /api/health. Used by the status bar
   * to render a green dot. Returns false on any non-2xx or transport
   * error so the UI can fall back gracefully. */
  async isAvailable(): Promise<boolean> {
    try {
      const res = await this.fetch("/api/health", { method: "GET" });
      return res.ok;
    } catch {
      return false;
    }
  }

  async listTemplates(): Promise<TemplateSummary[]> {
    const res = await this.fetch("/api/templates", { method: "GET" });
    if (!res.ok) return [];
    const data = (await res.json()) as { templates?: TemplateSummary[] };
    return Array.isArray(data.templates) ? data.templates : [];
  }

  async run(options: RunOptions): Promise<RunResult> {
    const timeout = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const startedAt = Date.now();
    const deadline = startedAt + timeout;
    const onProgress: ProgressHandler = options.onProgress ?? (() => undefined);

    const body = {
      yaml: options.yamlText ?? this.placeholderYamlForSlug(options.template),
      inputs: options.inputs ?? {},
      simulated: !!(options.simulated || options.dryRun),
      template_name: options.template ?? null,
    };

    const postRes = await this.fetch("/api/run", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Content-Type": "application/json" },
    });

    if (postRes.status === 401) {
      return this.failure("authentication required — set agentOrchestra.remoteToken", -1, "remote-401");
    }
    if (!postRes.ok) {
      const text = await safeText(postRes);
      return this.failure(`POST /api/run → ${postRes.status}: ${text}`.slice(0, 500), -1, "remote-error");
    }
    const { run_id: runId } = (await postRes.json()) as { run_id?: string };
    if (!runId) return this.failure("POST /api/run returned no run_id", -1, "remote-error");

    onProgress({
      eventCount: 0,
      message: `Run ${runId} started`,
    });

    let lastEventCount = 0;
    let lastDetail: ServerRunDetail | undefined;
    for (;;) {
      if (options.signal?.aborted) {
        return this.failure("run cancelled", -1, runId, lastDetail);
      }
      if (Date.now() > deadline) {
        return this.failure(`run did not finish in ${(timeout / 1000) | 0}s`, -1, runId, lastDetail);
      }
      const detailRes = await this.fetch(`/api/runs/${encodeURIComponent(runId)}`, { method: "GET" });
      if (!detailRes.ok) {
        return this.failure(`GET /api/runs/${runId} → ${detailRes.status}`, -1, runId, lastDetail);
      }
      lastDetail = (await detailRes.json()) as ServerRunDetail;
      const events = lastDetail.events ?? [];
      if (events.length > lastEventCount) {
        const newest = events[events.length - 1];
        onProgress({
          eventCount: events.length,
          message: shortDescription(newest),
          event: newest,
        });
        lastEventCount = events.length;
      }
      if (lastDetail.status === "completed" || lastDetail.status === "failed") break;
      await sleep(POLL_INTERVAL_MS);
    }

    const reportText = await this.fetchReport(runId);
    const finalContent = reportText || (lastDetail.final_content ?? "");
    const veto = lastDetail.veto_report ?? null;
    const vetoBlocked = !!(veto && veto.approved === false);
    const success = lastDetail.status === "completed" && !vetoBlocked;

    return {
      ok: success,
      success,
      mode: "remote",
      slug: options.template ?? null,
      spec: options.yamlPath ?? null,
      runId,
      status: lastDetail.status,
      durationSeconds: (Date.now() - startedAt) / 1000,
      reportUrl: `${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/report.md`,
      finalContent,
      vetoReport: veto,
      exitCode: vetoBlocked ? 4 : success ? 0 : 3,
    };
  }

  private async fetchReport(runId: string): Promise<string> {
    try {
      const res = await this.fetch(`/api/runs/${encodeURIComponent(runId)}/report.md`, { method: "GET" });
      if (!res.ok) return "";
      return await res.text();
    } catch {
      return "";
    }
  }

  private fetch(path: string, init: RequestInit = {}): Promise<Response> {
    const url = `${this.baseUrl.replace(/\/+$/, "")}${path}`;
    const headers = new Headers(init.headers);
    if (this.bearerToken) headers.set("Authorization", `Bearer ${this.bearerToken}`);
    if (!headers.has("Accept")) headers.set("Accept", "application/json");
    return fetch(url, { ...init, headers });
  }

  /** When the user picks a template by slug we send a stub YAML —
   * the backend resolves the slug via `RunBody.template_name`. */
  private placeholderYamlForSlug(slug?: string): string {
    return slug
      ? `# Resolved server-side from template_name: ${slug}\n`
      : "name: ad-hoc\ngoal: provided by inputs\n";
  }

  private failure(message: string, exitCode: number, runId: string, detail?: ServerRunDetail): RunResult {
    return {
      ok: false,
      success: false,
      mode: "remote",
      slug: null,
      runId: runId === "remote-401" || runId === "remote-error" ? null : runId,
      status: detail?.status ?? "failed",
      durationSeconds: 0,
      reportUrl: null,
      finalContent: detail?.final_content ?? "",
      vetoReport: detail?.veto_report ?? null,
      exitCode,
      errorMessage: message,
    };
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((res) => setTimeout(res, ms));
}

async function safeText(res: Response): Promise<string> {
  try {
    return await res.text();
  } catch {
    return "";
  }
}

function shortDescription(ev: WireEvent | undefined): string {
  if (!ev) return "running…";
  const role = typeof ev.role === "string" ? ` ${ev.role}` : "";
  const kind = typeof ev.kind === "string" ? ev.kind : ev.type;
  return `event:${kind}${role}`;
}
