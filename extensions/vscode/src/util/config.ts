/**
 * Settings + transport-resolver helper.
 *
 * One place to read every `agentOrchestra.*` workspace setting so the
 * commands + status bar agree on what's configured.
 */

import * as path from "node:path";
import * as vscode from "vscode";

import { LocalClient } from "../client/localClient";
import { RemoteClient } from "../client/remoteClient";
import type { OrchestrationClient } from "../client/types";

export type LocalCliMode = "auto" | "always" | "never";

export interface ResolvedConfig {
  serverUrl: string;
  localCliMode: LocalCliMode;
  defaultTemplate: string;
  remoteToken: string;
  workspacePath: string;
}

export function readConfig(): ResolvedConfig {
  const cfg = vscode.workspace.getConfiguration("agentOrchestra");
  const folderPath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd();
  return {
    serverUrl: (cfg.get<string>("serverUrl") ?? "http://localhost:8000").replace(/\/+$/, ""),
    localCliMode: (cfg.get<LocalCliMode>("localCli.enabled") ?? "auto"),
    defaultTemplate: cfg.get<string>("defaultTemplate") ?? "red-team-the-plan",
    remoteToken: cfg.get<string>("remoteToken") ?? "",
    workspacePath: cfg.get<string>("workspacePath") || path.join(folderPath, ".agent-orchestra-workspace"),
  };
}

/** Resolve the active transport once per command invocation.
 *
 * `auto`   → try local, fall back to remote.
 * `always` → require local (returns null if missing — caller surfaces an error).
 * `never`  → remote only.
 *
 * Returns null when no transport is reachable. The caller is
 * responsible for showing a helpful error to the user. */
export async function resolveClient(cfg: ResolvedConfig = readConfig()): Promise<OrchestrationClient | null> {
  if (cfg.localCliMode !== "never") {
    const local = await LocalClient.resolve();
    if (local && (await local.isAvailable())) return local;
    if (cfg.localCliMode === "always") return null;
  }
  const remote = new RemoteClient(cfg.serverUrl, cfg.remoteToken || undefined);
  if (await remote.isAvailable()) return remote;
  return null;
}
