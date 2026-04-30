/**
 * Tree view: the last N runs the user kicked off this session.
 *
 * In-memory only — surviving runs across VS Code restarts is a
 * roadmap item that wants the workspace state store.
 */

import * as vscode from "vscode";

import type { RunResult } from "../client/types";

const MAX_ENTRIES = 20;

export class RecentRunsTreeProvider implements vscode.TreeDataProvider<RunResult> {
  private readonly _emitter = new vscode.EventEmitter<RunResult | undefined>();
  readonly onDidChangeTreeData = this._emitter.event;
  private runs: RunResult[] = [];

  add(result: RunResult): void {
    this.runs.unshift(result);
    if (this.runs.length > MAX_ENTRIES) this.runs.length = MAX_ENTRIES;
    this._emitter.fire(undefined);
  }

  list(): readonly RunResult[] {
    return this.runs;
  }

  latest(): RunResult | undefined {
    return this.runs[0];
  }

  getTreeItem(run: RunResult): vscode.TreeItem {
    const label = run.slug ?? run.spec ?? run.runId ?? "run";
    const item = new vscode.TreeItem(label, vscode.TreeItemCollapsibleState.None);
    item.description = `${run.mode} · ${run.status} · ${run.durationSeconds.toFixed(1)}s`;
    item.tooltip = `Run ${run.runId ?? "?"} (exit ${run.exitCode})${run.errorMessage ? "\n" + run.errorMessage : ""}`;
    item.iconPath = new vscode.ThemeIcon(
      run.success ? "check" : run.exitCode === 4 ? "shield" : "error",
    );
    item.contextValue = "recentRun";
    if (run.reportPath || run.reportUrl) {
      item.command = {
        command: "agentOrchestra.viewLastReport",
        title: "View report",
        arguments: [run],
      };
    }
    return item;
  }

  getChildren(parent?: RunResult): RunResult[] {
    return parent ? [] : [...this.runs];
  }
}
