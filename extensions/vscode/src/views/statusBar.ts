/**
 * Single status-bar item that reports transport availability + the
 * latest run's outcome. Click → opens the dashboard command.
 *
 * Polled every 30 s so a backend coming online shows up without a
 * VS Code restart.
 */

import * as vscode from "vscode";

import { LocalClient } from "../client/localClient";
import { RemoteClient } from "../client/remoteClient";
import { readConfig } from "../util/config";

const POLL_INTERVAL_MS = 30_000;

export class StatusBarController {
  private readonly item: vscode.StatusBarItem;
  private timer?: NodeJS.Timeout;

  constructor() {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    this.item.command = "agentOrchestra.openDashboard";
    this.item.text = "$(sync) Orchestra";
    this.item.show();
  }

  async start(): Promise<void> {
    await this.refresh();
    this.timer = setInterval(() => void this.refresh(), POLL_INTERVAL_MS);
  }

  async refresh(): Promise<void> {
    const cfg = readConfig();
    let mode: "local" | "remote" | "offline" = "offline";
    if (cfg.localCliMode !== "never") {
      const local = await LocalClient.resolve();
      if (local && (await local.isAvailable())) mode = "local";
    }
    if (mode === "offline" && cfg.localCliMode !== "always") {
      const remote = new RemoteClient(cfg.serverUrl, cfg.remoteToken || undefined);
      if (await remote.isAvailable()) mode = "remote";
    }

    if (mode === "local") {
      this.item.text = "$(rocket) Orchestra · local";
      this.item.tooltip = `Local CLI ready (workspace: ${cfg.workspacePath})`;
      this.item.backgroundColor = undefined;
    } else if (mode === "remote") {
      this.item.text = "$(cloud) Orchestra · remote";
      this.item.tooltip = `Remote backend reachable: ${cfg.serverUrl}`;
      this.item.backgroundColor = undefined;
    } else {
      this.item.text = "$(warning) Orchestra · offline";
      this.item.tooltip = "Neither the local CLI nor the remote backend is reachable. Click for help.";
      this.item.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
    }
  }

  reportRun(success: boolean, label: string): void {
    this.item.text = success
      ? `$(check) Orchestra · ${label}`
      : `$(x) Orchestra · ${label}`;
    this.item.backgroundColor = success
      ? undefined
      : new vscode.ThemeColor("statusBarItem.errorBackground");
  }

  dispose(): void {
    if (this.timer) clearInterval(this.timer);
    this.item.dispose();
  }
}
