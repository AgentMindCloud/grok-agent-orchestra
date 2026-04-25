/**
 * Local-CLI transport — spawns `grok-orchestra run <spec> --json`.
 *
 * Mirrors the behaviour of `skills/agent-orchestra/scripts/run_orchestration.py`
 * (Prompt 17): line-buffered stderr drain so progress lines surface
 * to the webview as they arrive, captured stdout parsed for the
 * trailing JSON line, exit-code passed through.
 */

import * as cp from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

import type {
  OrchestrationClient,
  RunOptions,
  RunResult,
} from "./types";

const CLI_NAME = "grok-orchestra";
const DEFAULT_TIMEOUT_MS = 15 * 60 * 1_000;

export class LocalClient implements OrchestrationClient {
  public readonly mode = "local" as const;

  constructor(public readonly cliPath: string) {}

  /** Resolve the CLI on PATH. Returns a constructed client or null
   * (so callers can fall through to remote). */
  static async resolve(): Promise<LocalClient | null> {
    const found = await which(CLI_NAME);
    return found ? new LocalClient(found) : null;
  }

  /** Available iff the constructed `cliPath` exists. Cheaper than
   * spawning `--version` — VS Code calls this from the status bar
   * every few seconds. */
  async isAvailable(): Promise<boolean> {
    try {
      await fs.promises.access(this.cliPath, fs.constants.X_OK);
      return true;
    } catch {
      return false;
    }
  }

  async run(options: RunOptions): Promise<RunResult> {
    const startedAt = Date.now();
    const onProgress = options.onProgress ?? (() => undefined);

    const spec = options.template ?? options.yamlPath;
    if (!spec) {
      return this.failure("must provide template or yamlPath", -1);
    }

    const workspace = options.workspacePath ?? path.join(process.cwd(), ".agent-orchestra-workspace");
    fs.mkdirSync(workspace, { recursive: true });

    const args = [options.dryRun ? "dry-run" : "run", spec, "--json"];
    const env = { ...process.env, GROK_ORCHESTRA_WORKSPACE: workspace };

    const child = cp.spawn(this.cliPath, args, { env, stdio: ["ignore", "pipe", "pipe"] });
    let stdoutBuffer = "";
    const stderrLines: string[] = [];
    let eventCount = 0;

    options.signal?.addEventListener("abort", () => {
      child.kill("SIGTERM");
    });

    child.stdout.setEncoding("utf-8");
    child.stdout.on("data", (chunk: string) => {
      stdoutBuffer += chunk;
    });

    child.stderr.setEncoding("utf-8");
    child.stderr.on("data", (chunk: string) => {
      // The CLI emits one log line per event when --json is set;
      // forward each to the progress handler.
      const lines = chunk.split(/\r?\n/);
      for (const line of lines) {
        if (!line) continue;
        stderrLines.push(line);
        eventCount += 1;
        onProgress({ eventCount, message: line.slice(0, 160) });
      }
    });

    const exitCode = await new Promise<number>((resolve) => {
      const t = setTimeout(() => {
        child.kill("SIGKILL");
        resolve(-1);
      }, options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
      child.on("close", (code) => {
        clearTimeout(t);
        resolve(typeof code === "number" ? code : -1);
      });
    });

    const cliJson = parseLastJsonLine(stdoutBuffer);
    const finalContent = typeof cliJson?.final_content === "string" ? (cliJson.final_content as string) : "";
    const runId =
      (typeof cliJson?.run_id === "string" && (cliJson.run_id as string)) ||
      (typeof cliJson?.id === "string" && (cliJson.id as string)) ||
      latestRunDir(workspace);
    const veto =
      cliJson && typeof cliJson.veto_report === "object" && cliJson.veto_report
        ? (cliJson.veto_report as { approved: boolean; confidence?: number; reasons?: string[] })
        : null;
    const vetoBlocked = !!(veto && veto.approved === false) || exitCode === 4;
    const success = exitCode === 0 && !vetoBlocked;

    const reportPath = runId ? path.join(workspace, "runs", runId, "report.md") : null;
    const reportText =
      reportPath && fs.existsSync(reportPath) ? fs.readFileSync(reportPath, "utf-8") : "";

    return {
      ok: success,
      success,
      mode: "local",
      slug: options.template ?? null,
      spec: options.yamlPath ?? null,
      runId: runId || null,
      status: exitCode === 0 ? "completed" : "failed",
      durationSeconds: (Date.now() - startedAt) / 1000,
      reportPath: reportPath && fs.existsSync(reportPath) ? reportPath : null,
      finalContent: reportText || finalContent,
      vetoReport: veto,
      exitCode,
      errorMessage: exitCode === 0 ? undefined : stderrLines.slice(-3).join("\n").slice(0, 500),
    };
  }

  private failure(msg: string, exitCode: number): RunResult {
    return {
      ok: false,
      success: false,
      mode: "local",
      runId: null,
      status: "failed",
      durationSeconds: 0,
      finalContent: "",
      vetoReport: null,
      exitCode,
      errorMessage: msg,
    };
  }
}

/** Find an executable on PATH. Cross-platform. */
async function which(name: string): Promise<string | null> {
  const exts = process.platform === "win32" ? (process.env.PATHEXT ?? ".EXE;.CMD;.BAT").split(";") : [""];
  const dirs = (process.env.PATH ?? "").split(path.delimiter);
  for (const dir of dirs) {
    if (!dir) continue;
    for (const ext of exts) {
      const candidate = path.join(dir, name + ext);
      try {
        await fs.promises.access(candidate, fs.constants.X_OK);
        return candidate;
      } catch {
        continue;
      }
    }
  }
  return null;
}

function parseLastJsonLine(text: string): Record<string, unknown> | null {
  if (!text) return null;
  const lines = text.split(/\r?\n/).reverse();
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("{")) continue;
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      continue;
    }
  }
  return null;
}

function latestRunDir(workspace: string): string {
  const runsRoot = path.join(workspace, "runs");
  if (!fs.existsSync(runsRoot)) return "";
  const children = fs.readdirSync(runsRoot, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => ({ name: d.name, mtime: fs.statSync(path.join(runsRoot, d.name)).mtimeMs }))
    .sort((a, b) => b.mtime - a.mtime);
  return children[0]?.name ?? "";
}

// Suppress an "unused import" warning when the module is imported
// without the optional os check.
void os;
