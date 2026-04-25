/**
 * Extension entry point. Wires up:
 *   - Status bar (transport availability + last-run outcome)
 *   - Tree views (templates, recent runs)
 *   - 5 commands (runCurrentFile / runTemplate / openDashboard /
 *     viewLastReport / compareRuns)
 *
 * The webview is created on demand by the run commands — there's no
 * "always-on" heavy state.
 */

import * as vscode from "vscode";

import { registerCommands } from "./commands";
import type { RunCommandDeps } from "./commands/runOrchestra";
import { RecentRunsTreeProvider } from "./views/recentRunsTree";
import { StatusBarController } from "./views/statusBar";
import { TemplatesTreeProvider } from "./views/templatesTree";

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const status = new StatusBarController();
  await status.start();
  context.subscriptions.push(status);

  const templatesProvider = new TemplatesTreeProvider();
  const templatesView = vscode.window.createTreeView("agentOrchestra.templates", {
    treeDataProvider: templatesProvider,
  });
  context.subscriptions.push(templatesView);
  templatesProvider.refresh();

  const recent = new RecentRunsTreeProvider();
  const recentView = vscode.window.createTreeView("agentOrchestra.recentRuns", {
    treeDataProvider: recent,
  });
  context.subscriptions.push(recentView);

  const deps: RunCommandDeps = { context, recent, status };
  context.subscriptions.push(...registerCommands(deps));

  // Refresh tree views when configuration changes — the
  // serverUrl might have moved, the local CLI may have been
  // installed mid-session, etc.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("agentOrchestra")) {
        templatesProvider.refresh();
        void status.refresh();
      }
    }),
  );
}

export function deactivate(): void {
  /* nothing to clean up — every subscription is in context.subscriptions */
}
