/**
 * Typed thin wrapper around `fetch`. Every method is async, returns
 * a typed payload, and throws `ApiError` on non-2xx responses.
 *
 * Default base URL is `process.env.NEXT_PUBLIC_API_URL` (set in
 * `.env.local`). Tests can pass a custom base + a custom `fetch`
 * implementation to swap in `msw` / a stub.
 */

import type {
  DryRunBody,
  DryRunResponse,
  HealthResponse,
  RunBody,
  RunCreateResponse,
  RunDetail,
  RunsListResponse,
  TemplateDetail,
  TemplatesListResponse,
  ValidateBody,
  ValidateResponse,
} from "@/types/api";

export class ApiError extends Error {
  status: number;
  detail?: string;
  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetch?: typeof fetch;
}

const DEFAULT_BASE = "http://localhost:8000";

/**
 * Resolve the active backend base URL.
 *
 * Order: explicit option → `NEXT_PUBLIC_API_URL` → `DEFAULT_BASE`.
 * Trailing slashes are stripped.
 */
export function resolveBaseUrl(opts?: ApiClientOptions): string {
  const raw =
    opts?.baseUrl ??
    (typeof process !== "undefined"
      ? process.env.NEXT_PUBLIC_API_URL
      : undefined) ??
    DEFAULT_BASE;
  return raw.replace(/\/+$/, "");
}

/**
 * Resolve the WebSocket origin from the same source as the API base.
 * Honours `NEXT_PUBLIC_WS_URL` if set, otherwise swaps `http[s]://`
 * for `ws[s]://` on the resolved API base.
 */
export function resolveWsUrl(opts?: ApiClientOptions): string {
  const explicit =
    typeof process !== "undefined"
      ? process.env.NEXT_PUBLIC_WS_URL
      : undefined;
  if (explicit) return explicit.replace(/\/+$/, "");
  const base = resolveBaseUrl(opts);
  return base.replace(/^http(s?):\/\//, "ws$1://");
}

export class ApiClient {
  private base: string;
  private fetchImpl: typeof fetch;

  constructor(opts?: ApiClientOptions) {
    this.base = resolveBaseUrl(opts);
    this.fetchImpl = opts?.fetch ?? fetch.bind(globalThis);
  }

  // ----- low-level helpers -------------------------------------------- #

  private async request<T>(
    path: string,
    init?: RequestInit & { json?: unknown },
  ): Promise<T> {
    const url = `${this.base}${path}`;
    const headers = new Headers(init?.headers);
    let body: BodyInit | undefined = init?.body ?? undefined;
    if (init?.json !== undefined) {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(init.json);
    }
    if (!headers.has("Accept")) headers.set("Accept", "application/json");
    const res = await this.fetchImpl(url, {
      ...init,
      body,
      headers,
    });
    if (!res.ok) {
      let detail: string | undefined;
      try {
        const blob = await res.json();
        detail = typeof blob.detail === "string" ? blob.detail : undefined;
      } catch {
        /* non-JSON error body — drop */
      }
      throw new ApiError(
        res.status,
        `${init?.method ?? "GET"} ${path} → ${res.status}`,
        detail,
      );
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  // ----- public API --------------------------------------------------- #

  health(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/api/health");
  }

  listTemplates(tag?: string): Promise<TemplatesListResponse> {
    const qs = tag ? `?tag=${encodeURIComponent(tag)}` : "";
    return this.request<TemplatesListResponse>(`/api/templates${qs}`);
  }

  getTemplate(name: string): Promise<TemplateDetail> {
    return this.request<TemplateDetail>(
      `/api/templates/${encodeURIComponent(name)}`,
    );
  }

  validate(body: ValidateBody): Promise<ValidateResponse> {
    return this.request<ValidateResponse>("/api/validate", {
      method: "POST",
      json: body,
    });
  }

  dryRun(body: DryRunBody): Promise<DryRunResponse> {
    return this.request<DryRunResponse>("/api/dry-run", {
      method: "POST",
      json: body,
    });
  }

  startRun(body: RunBody): Promise<RunCreateResponse> {
    return this.request<RunCreateResponse>("/api/run", {
      method: "POST",
      json: body,
    });
  }

  listRuns(): Promise<RunsListResponse> {
    return this.request<RunsListResponse>("/api/runs");
  }

  getRun(runId: string): Promise<RunDetail> {
    return this.request<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`);
  }

  reportUrl(
    runId: string,
    format: "md" | "pdf" | "docx",
  ): string {
    return `${this.base}/api/runs/${encodeURIComponent(runId)}/report.${format}`;
  }

  wsUrl(runId: string): string {
    const wsBase = resolveWsUrl({ baseUrl: this.base });
    return `${wsBase}/ws/runs/${encodeURIComponent(runId)}`;
  }
}

// A module-singleton for app-router server components + hooks. Tests
// should construct their own instance with a mock fetch instead of
// importing this default.
export const api = new ApiClient();
