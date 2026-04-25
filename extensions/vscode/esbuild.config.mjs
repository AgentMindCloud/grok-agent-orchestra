// Two-bundle esbuild config: the extension host bundle (Node CommonJS,
// `vscode` external) + the webview bundle (browser ESM, React inlined).
// Run `node esbuild.config.mjs` for a dev build, `--production` for a
// minified release build, `--watch` for the dev watch loop.

import { build, context } from "esbuild";

const flags = new Set(process.argv.slice(2));
const watch = flags.has("--watch");
const production = flags.has("--production");

const common = {
  bundle: true,
  sourcemap: !production,
  minify: production,
  logLevel: "info",
  target: "node18",
};

/** Extension host (runs in Node inside the VS Code extension process). */
const extensionConfig = {
  ...common,
  entryPoints: ["src/extension.ts"],
  outfile: "dist/extension.js",
  platform: "node",
  format: "cjs",
  external: ["vscode"],
};

/** Webview UI (runs in a sandboxed Chromium tab; bundles React). */
const webviewConfig = {
  ...common,
  entryPoints: ["src/webview/ui/index.tsx"],
  outfile: "dist/webview.js",
  platform: "browser",
  format: "iife",
  jsx: "automatic",
  target: ["es2022"],
};

async function run() {
  if (watch) {
    const ext = await context(extensionConfig);
    const ui = await context(webviewConfig);
    await Promise.all([ext.watch(), ui.watch()]);
    console.log("[esbuild] watching…");
    return;
  }
  await Promise.all([build(extensionConfig), build(webviewConfig)]);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
