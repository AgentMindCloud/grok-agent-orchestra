/**
 * Debate-stream webview panel — single instance, reveals on every run.
 *
 * The panel hosts a minimal React app (`src/webview/ui/`) bundled to
 * `dist/webview.js`. The extension posts `Outbound` messages
 * (`init` → `progress`* → `result`); the webview replies with
 * `Inbound` (`ready`, `open-report`, `cancel`).
 */

import * as crypto from "node:crypto";
import * as vscode from "vscode";

import type { ProgressUpdate, RunResult } from "../client/types";
import type { Inbound, Outbound } from "../util/messages";

export class DebatePanel {
  private static current?: DebatePanel;

  static show(extensionUri: vscode.Uri, mode: "local" | "remote"): DebatePanel {
    if (DebatePanel.current) {
      DebatePanel.current.panel.reveal(vscode.ViewColumn.Beside);
      DebatePanel.current.send({ type: "init", mode, theme: detectTheme() });
      return DebatePanel.current;
    }
    const panel = vscode.window.createWebviewPanel(
      "agentOrchestra.debate",
      "Agent Orchestra · debate",
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(extensionUri, "dist"), vscode.Uri.joinPath(extensionUri, "media")],
      },
    );
    DebatePanel.current = new DebatePanel(panel, extensionUri, mode);
    return DebatePanel.current;
  }

  private constructor(
    private readonly panel: vscode.WebviewPanel,
    private readonly extensionUri: vscode.Uri,
    initialMode: "local" | "remote",
  ) {
    panel.onDidDispose(() => {
      DebatePanel.current = undefined;
    });
    panel.webview.html = this.renderHtml();
    panel.webview.onDidReceiveMessage((message: Inbound) => this.handleInbound(message));
    this.send({ type: "init", mode: initialMode, theme: detectTheme() });
  }

  postProgress(update: ProgressUpdate): void {
    this.send({
      type: "progress",
      eventCount: update.eventCount,
      message: update.message,
      event: update.event,
    });
  }

  postResult(result: RunResult): void {
    this.send({ type: "result", result });
  }

  postLog(level: "info" | "warn" | "error", text: string): void {
    this.send({ type: "log", level, text });
  }

  private send(message: Outbound): void {
    void this.panel.webview.postMessage(message);
  }

  private handleInbound(message: Inbound): void {
    if (!message || typeof message !== "object") return;
    if (message.type === "open-report") {
      if (message.path) {
        void vscode.workspace.openTextDocument(message.path).then(
          (doc) => vscode.window.showTextDocument(doc, { preview: false }),
        );
      } else if (message.url) {
        void vscode.env.openExternal(vscode.Uri.parse(message.url));
      }
    }
    // `ready` is informational; `cancel` is reserved for a future
    // in-panel cancel button — the run already accepts a CancellationToken
    // wired through `withProgress`, which the user can cancel from
    // the toast.
  }

  private renderHtml(): string {
    const nonce = crypto.randomBytes(16).toString("base64");
    const scriptUri = this.panel.webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, "dist", "webview.js"),
    );
    const csp = [
      "default-src 'none'",
      `style-src ${this.panel.webview.cspSource} 'unsafe-inline'`,
      `script-src 'nonce-${nonce}'`,
      `font-src ${this.panel.webview.cspSource}`,
      `img-src ${this.panel.webview.cspSource} https: data:`,
    ].join("; ");

    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta http-equiv="Content-Security-Policy" content="${csp}" />
<title>Agent Orchestra · debate</title>
<style>
  :root { color-scheme: var(--vscode-color-scheme, dark); }
  * { box-sizing: border-box; }
  html, body, #root {
    margin: 0; padding: 0; height: 100%;
    background: var(--vscode-editor-background);
    color: var(--vscode-foreground);
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    line-height: 1.5;
  }
  pre, code { font-family: var(--vscode-editor-font-family, monospace); }
</style>
</head>
<body>
<div id="root"></div>
<script nonce="${nonce}" src="${scriptUri.toString()}"></script>
</body>
</html>`;
  }
}

function detectTheme(): "light" | "dark" {
  const kind = vscode.window.activeColorTheme.kind;
  return kind === vscode.ColorThemeKind.Light || kind === vscode.ColorThemeKind.HighContrastLight
    ? "light"
    : "dark";
}
