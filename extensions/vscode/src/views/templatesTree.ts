/**
 * Tree view: bundled Agent Orchestra templates, grouped by category.
 *
 * Templates come from the active backend's `/api/templates` (when
 * remote is reachable) or fall back to a small built-in list so
 * the tree is never empty. Selecting a leaf invokes
 * `agentOrchestra.runTemplate` pre-filled with that slug.
 */

import * as vscode from "vscode";

import type { TemplateSummary } from "../client/types";
import { RemoteClient } from "../client/remoteClient";
import { readConfig } from "../util/config";

interface CategoryNode {
  kind: "category";
  label: string;
  children: TemplateSummary[];
}

type Node = CategoryNode | TemplateSummary;

const FALLBACK_TEMPLATES: TemplateSummary[] = [
  { slug: "red-team-the-plan", name: "Red-team the Plan", categories: ["debate", "fast"], estimatedTokens: 8000 },
  { slug: "competitive-analysis", name: "Competitive Analysis", categories: ["research", "business"], estimatedTokens: 18000 },
  { slug: "due-diligence-investor-memo", name: "Investor Memo (DD)", categories: ["business", "research"], estimatedTokens: 20000 },
  { slug: "paper-summarizer", name: "Paper Summarizer", categories: ["research"], estimatedTokens: 15000 },
  { slug: "weekly-news-digest", name: "Weekly News Digest", categories: ["fast", "web-search"], estimatedTokens: 12000 },
  { slug: "orchestra-debate-loop-policy", name: "Policy Debate Loop", categories: ["debate", "deep"], estimatedTokens: 25000 },
];

export class TemplatesTreeProvider implements vscode.TreeDataProvider<Node> {
  private readonly _emitter = new vscode.EventEmitter<Node | undefined>();
  readonly onDidChangeTreeData = this._emitter.event;
  private cache: TemplateSummary[] = FALLBACK_TEMPLATES;

  refresh(): void {
    this._emitter.fire(undefined);
    void this.populate();
  }

  async populate(): Promise<void> {
    const cfg = readConfig();
    try {
      const remote = new RemoteClient(cfg.serverUrl, cfg.remoteToken || undefined);
      if (await remote.isAvailable()) {
        const fetched = await remote.listTemplates();
        if (fetched.length) {
          this.cache = fetched;
          this._emitter.fire(undefined);
        }
      }
    } catch {
      // Silent — fall back to the built-in list.
    }
  }

  getTreeItem(node: Node): vscode.TreeItem {
    if ("kind" in node) {
      const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.Expanded);
      item.iconPath = new vscode.ThemeIcon("folder");
      item.contextValue = "category";
      return item;
    }
    const tpl = node;
    const item = new vscode.TreeItem(tpl.name ?? tpl.slug, vscode.TreeItemCollapsibleState.None);
    item.description = tpl.estimatedTokens ? `~${tpl.estimatedTokens} tok` : tpl.slug;
    item.tooltip = tpl.description ?? tpl.slug;
    item.iconPath = new vscode.ThemeIcon("file-symlink-file");
    item.contextValue = "template";
    item.command = {
      command: "agentOrchestra.runTemplate",
      title: "Run template",
      arguments: [tpl.slug],
    };
    return item;
  }

  getChildren(parent?: Node): Node[] {
    if (!parent) {
      const groups = new Map<string, TemplateSummary[]>();
      for (const tpl of this.cache) {
        const cat = (tpl.categories?.[0] ?? "other").toLowerCase();
        const list = groups.get(cat) ?? [];
        list.push(tpl);
        groups.set(cat, list);
      }
      return [...groups.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([label, children]) => ({ kind: "category" as const, label, children }));
    }
    if ("kind" in parent && parent.kind === "category") return parent.children;
    return [];
  }
}
