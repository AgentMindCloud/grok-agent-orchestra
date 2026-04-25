/**
 * The five user-facing commands. Each is a thin wrapper around
 * `runOrchestration` (for run-style commands) or a direct VS Code
 * API call (for view / open / compare).
 */

import * as vscode from "vscode";

import type { RunResult, TemplateSummary } from "../client/types";
import { readConfig } from "../util/config";
import { RemoteClient } from "../client/remoteClient";
import type { RecentRunsTreeProvider } from "../views/recentRunsTree";
import { runOrchestration, type RunCommandDeps } from "./runOrchestra";

export function registerCommands(deps: RunCommandDeps): vscode.Disposable[] {
  return [
    vscode.commands.registerCommand("agentOrchestra.runCurrentFile", () => runCurrentFile(deps)),
    vscode.commands.registerCommand("agentOrchestra.runTemplate", (slug?: string) => runTemplate(deps, slug)),
    vscode.commands.registerCommand("agentOrchestra.openDashboard", () => openDashboard()),
    vscode.commands.registerCommand("agentOrchestra.viewLastReport", (run?: RunResult) =>
      viewLastReport(deps.recent, run),
    ),
    vscode.commands.registerCommand("agentOrchestra.compareRuns", () => compareRuns(deps.recent)),
  ];
}

async function runCurrentFile(deps: RunCommandDeps): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "yaml") {
    void vscode.window.showErrorMessage("Open a YAML file before running this command.");
    return;
  }
  const yamlPath = editor.document.uri.fsPath;
  const yamlText = editor.document.getText();
  await runOrchestration(deps, { yamlPath, yamlText });
}

async function runTemplate(deps: RunCommandDeps, preselectedSlug?: string): Promise<void> {
  const slug = preselectedSlug ?? (await pickTemplate());
  if (!slug) return;
  const simulated = await pickMode();
  if (simulated === undefined) return;
  await runOrchestration(deps, { template: slug, simulated });
}

async function pickTemplate(): Promise<string | undefined> {
  const cfg = readConfig();
  let templates: TemplateSummary[] = [];
  try {
    const remote = new RemoteClient(cfg.serverUrl, cfg.remoteToken || undefined);
    if (await remote.isAvailable()) {
      templates = await remote.listTemplates();
    }
  } catch {
    /* fall through to default-only */
  }
  if (templates.length === 0) {
    templates = [{ slug: cfg.defaultTemplate, name: cfg.defaultTemplate }];
  }
  const items: vscode.QuickPickItem[] = templates.map((t) => ({
    label: t.name ?? t.slug,
    description: t.estimatedTokens ? `~${t.estimatedTokens} tok` : t.slug,
    detail: t.description,
  }));
  const picked = await vscode.window.showQuickPick(items, {
    placeHolder: "Pick a template to run",
    matchOnDescription: true,
    matchOnDetail: true,
  });
  if (!picked) return undefined;
  // Map back: the label may be the human name; find by index.
  const idx = items.indexOf(picked);
  return templates[idx]?.slug;
}

async function pickMode(): Promise<boolean | undefined> {
  const choice = await vscode.window.showQuickPick(
    [
      { label: "Simulated", description: "No live API calls — uses canned events.", value: true },
      { label: "Live", description: "Hits the configured providers (uses credits).", value: false },
    ],
    { placeHolder: "Run live or simulated?" },
  );
  return choice?.value;
}

function openDashboard(): void {
  const cfg = readConfig();
  void vscode.env.openExternal(vscode.Uri.parse(cfg.serverUrl));
}

async function viewLastReport(recent: RecentRunsTreeProvider, runArg?: RunResult): Promise<void> {
  const run = runArg ?? recent.latest();
  if (!run) {
    void vscode.window.showInformationMessage("No runs in this session yet.");
    return;
  }
  if (run.reportPath) {
    const doc = await vscode.workspace.openTextDocument(run.reportPath);
    await vscode.window.showTextDocument(doc, { preview: false });
    return;
  }
  if (run.reportUrl) {
    void vscode.env.openExternal(vscode.Uri.parse(run.reportUrl));
    return;
  }
  void vscode.window.showInformationMessage("Last run hasn't produced a report yet.");
}

async function compareRuns(recent: RecentRunsTreeProvider): Promise<void> {
  const list = recent.list();
  if (list.length < 2) {
    void vscode.window.showInformationMessage("Need at least two runs in this session to compare.");
    return;
  }
  const items = list.map((r, i) => ({
    label: `${i + 1}. ${r.slug ?? r.spec ?? r.runId ?? "run"}`,
    description: `${r.mode} · ${r.status}`,
    run: r,
  }));
  const left = await vscode.window.showQuickPick(items, { placeHolder: "Pick the first run" });
  if (!left) return;
  const right = await vscode.window.showQuickPick(
    items.filter((i) => i !== left),
    { placeHolder: "Pick the second run" },
  );
  if (!right) return;

  const leftUri = await runToUri(left.run);
  const rightUri = await runToUri(right.run);
  if (!leftUri || !rightUri) {
    void vscode.window.showErrorMessage("One of the selected runs has no readable report.");
    return;
  }
  await vscode.commands.executeCommand("vscode.diff", leftUri, rightUri, "Agent Orchestra · compare");
}

async function runToUri(run: RunResult): Promise<vscode.Uri | null> {
  if (run.reportPath) return vscode.Uri.file(run.reportPath);
  if (run.reportUrl) return vscode.Uri.parse(run.reportUrl);
  return null;
}
