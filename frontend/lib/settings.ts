/**
 * Per-browser preferences. Lives entirely in `localStorage` — nothing
 * is sent server-side. The set of fields mirrors what 16d's expanded
 * Settings page exposes:
 *
 *   - `apiBaseUrl` — overrides `NEXT_PUBLIC_API_URL`
 *   - `defaultWorkflow` — pre-selects the workflow on the dashboard
 *   - `defaultModel` — pre-selects the LLM provider/model
 *   - `modelAliases` — UI for the YAML aliases from Prompt 9
 *   - `tracing` — LangSmith enable + project name (key stays
 *      server-side)
 *   - `density` — `cozy` (default) or `compact`
 *
 * Theme is owned by `next-themes`; we don't double-store it.
 *
 * Format is forward-compatible: unknown keys are dropped on read,
 * missing keys fall back to the schema defaults. Bumping
 * `SETTINGS_VERSION` and deleting unsupported keys lets us reshape
 * the store later without crashing on stale localStorage entries.
 */

export const SETTINGS_VERSION = 1;
const STORAGE_KEY = "grok-orchestra:settings";

export type Density = "cozy" | "compact";
export type WorkflowKind =
  | "auto"
  | "native"
  | "simulated"
  | "deep_research";

export interface ModelAlias {
  alias: string;
  provider: string;
  model: string;
}

export interface Settings {
  schemaVersion: number;
  apiBaseUrl: string;
  defaultWorkflow: WorkflowKind;
  defaultModel: string;
  modelAliases: ModelAlias[];
  tracing: {
    enabled: boolean;
    project: string;
  };
  density: Density;
}

export const DEFAULT_SETTINGS: Settings = {
  schemaVersion: SETTINGS_VERSION,
  apiBaseUrl: "",
  defaultWorkflow: "auto",
  defaultModel: "grok-4-0709",
  modelAliases: [],
  tracing: { enabled: false, project: "grok-agent-orchestra" },
  density: "cozy",
};

export function loadSettings(): Settings {
  if (typeof window === "undefined") return DEFAULT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<Settings>;
    return mergeWithDefaults(parsed);
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(s: Settings): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ ...s, schemaVersion: SETTINGS_VERSION }),
  );
  document.documentElement.dataset.density = s.density;
}

export function clearSettings(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
  delete document.documentElement.dataset.density;
}

function mergeWithDefaults(raw: Partial<Settings>): Settings {
  return {
    schemaVersion: SETTINGS_VERSION,
    apiBaseUrl: typeof raw.apiBaseUrl === "string" ? raw.apiBaseUrl : "",
    defaultWorkflow:
      raw.defaultWorkflow && WORKFLOWS.includes(raw.defaultWorkflow as WorkflowKind)
        ? (raw.defaultWorkflow as WorkflowKind)
        : DEFAULT_SETTINGS.defaultWorkflow,
    defaultModel:
      typeof raw.defaultModel === "string" ? raw.defaultModel : DEFAULT_SETTINGS.defaultModel,
    modelAliases: Array.isArray(raw.modelAliases)
      ? raw.modelAliases.filter(isModelAlias)
      : [],
    tracing: {
      enabled: !!raw.tracing?.enabled,
      project:
        typeof raw.tracing?.project === "string" && raw.tracing.project
          ? raw.tracing.project
          : DEFAULT_SETTINGS.tracing.project,
    },
    density: raw.density === "compact" ? "compact" : "cozy",
  };
}

const WORKFLOWS: WorkflowKind[] = ["auto", "native", "simulated", "deep_research"];

function isModelAlias(v: unknown): v is ModelAlias {
  if (!v || typeof v !== "object") return false;
  const a = v as Record<string, unknown>;
  return (
    typeof a.alias === "string" &&
    typeof a.provider === "string" &&
    typeof a.model === "string"
  );
}

export const KNOWN_PROVIDERS = [
  "xai",
  "openai",
  "anthropic",
  "ollama",
  "mistral",
  "groq",
  "together",
  "bedrock",
  "azure",
] as const;
