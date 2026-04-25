/**
 * Extension smoke tests. Run via `npm test` which boots a temporary
 * VS Code instance with the built extension loaded. Pure
 * activation + contribution wiring — no live runs.
 *
 * The CI workflow (.github/workflows/vscode-extension.yml) runs
 * lint + typecheck + package on every PR; these tests run only
 * when a developer wants the slower smoke loop locally.
 */

import * as assert from "node:assert";
import * as vscode from "vscode";

suite("Agent Orchestra extension", () => {
  test("registers all five commands", async () => {
    const all = await vscode.commands.getCommands(true);
    for (const id of [
      "agentOrchestra.runCurrentFile",
      "agentOrchestra.runTemplate",
      "agentOrchestra.openDashboard",
      "agentOrchestra.viewLastReport",
      "agentOrchestra.compareRuns",
    ]) {
      assert.ok(all.includes(id), `missing command: ${id}`);
    }
  });

  test("contributes the agentOrchestra activity-bar view container", () => {
    const ext = vscode.extensions.getExtension("agentmindcloud.agent-orchestra");
    assert.ok(ext, "extension not found by id");
    const containers = ext!.packageJSON.contributes?.viewsContainers?.activitybar ?? [];
    assert.ok(
      containers.find((c: { id: string }) => c.id === "agentOrchestra"),
      "agentOrchestra activity-bar container missing",
    );
  });

  test("contributes the orchestra YAML schema for *.orchestra.yaml", () => {
    const ext = vscode.extensions.getExtension("agentmindcloud.agent-orchestra");
    assert.ok(ext);
    const yamlValidation = ext!.packageJSON.contributes?.yamlValidation ?? [];
    const entry = yamlValidation.find((y: { url: string }) => y.url.includes("orchestra.schema.json"));
    assert.ok(entry, "orchestra.schema.json contribution missing");
    assert.deepStrictEqual(entry.fileMatch, ["**/*.orchestra.yaml", "**/*.orchestra.yml"]);
  });

  test("status bar item is created on activation", async () => {
    const ext = vscode.extensions.getExtension("agentmindcloud.agent-orchestra");
    if (ext && !ext.isActive) await ext.activate();
    // We can't query VS Code's status-bar items directly — but if
    // activation didn't throw, the StatusBarController constructed
    // its `vscode.window.createStatusBarItem` successfully.
    assert.ok(ext?.isActive, "extension failed to activate");
  });
});
