/**
 * Hand-written shapes mirroring the FastAPI backend
 * (`grok_orchestra/web/main.py`). Keep these in sync with the
 * backend until `pnpm generate:types` runs against a live
 * `/openapi.json` and produces `types/api.generated.ts`.
 */

export type RunStatus = "pending" | "running" | "completed" | "failed";

export type TemplateCategory =
  | "research"
  | "business"
  | "technical"
  | "debate"
  | "fast"
  | "deep"
  | "local-docs"
  | "web-search"
  | "other";

export interface TemplateSummary {
  name: string;
  description: string;
  tags: string[];
  category: TemplateCategory;
  yaml_preview?: string;
}

export interface TemplateDetail extends TemplateSummary {
  yaml: string;
  inputs?: Record<string, unknown>;
}

export interface ValidateBody {
  yaml: string;
}

export interface ValidateResponse {
  ok: boolean;
  errors?: string[];
  resolved_mode?: string;
}

export interface DryRunBody {
  yaml: string;
  inputs?: Record<string, unknown>;
}

export interface DryRunResponse {
  events: WireEvent[];
  final_output: string;
  veto_report?: VetoReport | null;
}

export interface RunBody {
  yaml: string;
  inputs?: Record<string, unknown>;
  simulated?: boolean;
  template_name?: string;
}

export interface RunCreateResponse {
  run_id: string;
}

export interface VetoReport {
  approved: boolean;
  confidence?: number;
  reasons?: string[];
}

export interface RunSummary {
  id: string;
  template_name?: string | null;
  simulated: boolean;
  status: RunStatus;
  started_at: string;
  completed_at?: string | null;
  final_output?: string | null;
  veto_report?: VetoReport | null;
}

export interface RunDetail extends RunSummary {
  yaml_text: string;
  inputs: Record<string, unknown>;
  events: WireEvent[];
}

export interface RunsListResponse {
  runs: RunSummary[];
}

export interface HealthResponse {
  status: "ok";
  version: string;
}

export interface TemplatesListResponse {
  templates: TemplateSummary[];
  count?: number;
}

// --------------------------------------------------------------------------- #
// WebSocket frame envelope. Every backend event is a JSON object
// with a `type` discriminator. The shape isn't lockable to a tagged
// union without dependency on the backend's internal Event types,
// so we model it loosely + provide narrowing helpers in `lib/events.ts`.
// --------------------------------------------------------------------------- #

export interface WireEvent {
  type: string;
  seq?: number;
  ts?: string;
  // Free-form payload — common keys: role, text, kind, error, run.
  [key: string]: unknown;
}
