/**
 * Shared command core: takes a `RunOptions`, resolves the transport,
 * opens the debate webview, and pushes the result into the recent-runs
 * tree + status bar.
 *
 * The four user-facing run commands (current file, template picker,
 * dashboard, view-last-report) all funnel through here so the
 * progress reporting stays consistent.
 */

import * as fs from "node:fs";
import * as vscode from "vscode";

import type { RunOptions, RunResult } from "../client/types";
import { DebatePanel } from "../webview/DebatePanel";
import { resolveClient, readConfig } from "../util/config";
import { RecentRunsTreeProvider } from "../views/recentRunsTree";
import { StatusBarController } from "../views/statusBar";

export interface RunCommandDeps {
  context: vscode.ExtensionContext;
  recent: RecentRunsTreeProvider;
  status: StatusBarController;
}

export async function runOrchestration(
  deps: RunCommandDeps,
  request: { template?: string; yamlPath?: string; yamlText?: string; simulated?: boolean; dryRun?: boolean; inputs?: Record<string, unknown> },
): Promise<RunResult | null> {
  const cfg = readConfig();
  const client = await resolveClient(cfg);
  if (!client) {
    const choice = await vscode.window.showErrorMessage(
      "Agent Orchestra: neither the local CLI nor the remote backend is reachable.",
      "Open settings",
      "Install CLI",
    );
    if (choice === "Open settings") {
      void vscode.commands.executeCommand("workbench.action.openSettings", "agentOrchestra");
    } else if (choice === "Install CLI") {
      void vscode.env.openExternal(vscode.Uri.parse("https://pypi.org/project/grok-agent-orchestra/"));
    }
    return null;
  }

  const panel = DebatePanel.show(deps.context.extensionUri, client.mode);

  const options: RunOptions = {
    template: request.template,
    yamlPath: request.yamlPath,
    yamlText: request.yamlText ?? (request.yamlPath ? readYaml(request.yamlPath) : undefined),
    inputs: request.inputs ?? {},
    simulated: !!request.simulated,
    dryRun: !!request.dryRun,
    bearerToken: cfg.remoteToken || undefined,
    workspacePath: cfg.workspacePath,
    onProgress: (update) => panel.postProgress(update),
  };

  let result: RunResult | null = null;
  try {
    result = await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: `Agent Orchestra · ${request.template ?? "current file"}`,
        cancellable: true,
      },
      async (_progress, token) => {
        const ctrl = new AbortController();
        token.onCancellationRequested(() => ctrl.abort());
        return client.run({ ...options, signal: ctrl.signal });
      },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    void vscode.window.showErrorMessage(`Agent Orchestra run failed: ${message}`);
    return null;
  }

  panel.postResult(result);
  deps.recent.add(result);
  deps.status.reportRun(
    result.success,
    result.success
      ? `${request.template ?? "ok"} ✓`
      : result.exitCode === 4
        ? "vetoed"
        : "failed",
  );

  if (result.exitCode === 4) {
    void vscode.window.showWarningMessage(
      `Lucas vetoed the synthesis: ${result.vetoReport?.reasons?.[0] ?? "no reason given"}`,
    );
  } else if (!result.success && result.errorMessage) {
    void vscode.window.showErrorMessage(`Run failed: ${result.errorMessage}`);
  }

  return result;
}

function readYaml(p: string): string | undefined {
  try {
    return fs.readFileSync(p, "utf-8");
  } catch {
    return undefined;
  }
}
