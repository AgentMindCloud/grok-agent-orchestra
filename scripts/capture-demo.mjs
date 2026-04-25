#!/usr/bin/env node
/**
 * Capture a 30-second demo of the courtroom debate visualization for
 * the README hero. Drives a real browser via Playwright against a
 * local dev stack (`docker compose -f docker-compose.yml -f
 * docker-compose.dev.yml up`).
 *
 * Output: docs/images/web-ui-debate.gif (or .mp4 if --format=mp4).
 *
 * Usage:
 *   node scripts/capture-demo.mjs                 # default: 30s, gif
 *   node scripts/capture-demo.mjs --format=mp4    # mp4 instead
 *   node scripts/capture-demo.mjs --template=red-team-the-plan
 *
 * Prereqs:
 *   - The dev compose stack is running (FastAPI on :8000, Next on :3000).
 *   - playwright is installed: `cd frontend && pnpm add -D playwright @playwright/test`
 *   - For .gif output: `npm i -g gifski` (or set --format=mp4 to skip).
 *
 * NOTE: This script is environment-sensitive — it spawns a real
 * browser. CI does not run it. Capture once locally per release and
 * commit the artefact.
 */

import { mkdirSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const OUT_DIR = resolve(ROOT, "docs", "images");
const OUT_PATH_GIF = resolve(OUT_DIR, "web-ui-debate.gif");
const OUT_PATH_MP4 = resolve(OUT_DIR, "web-ui-debate.mp4");

function arg(name, fallback) {
  const flag = process.argv.find((a) => a.startsWith(`--${name}=`));
  return flag ? flag.split("=").slice(1).join("=") : fallback;
}

const FORMAT = arg("format", "mp4");
const TEMPLATE = arg("template", "red-team-the-plan");
const DURATION_MS = Number(arg("duration", "30000"));
const FRONTEND_URL = arg("frontend", "http://localhost:3000");
const API_URL = arg("api", "http://localhost:8000");

async function main() {
  let chromium;
  try {
    ({ chromium } = await import("playwright"));
  } catch (e) {
    console.error(
      "playwright is not installed. Run:\n  cd frontend && pnpm add -D playwright @playwright/test\n  pnpm exec playwright install chromium",
    );
    process.exit(2);
  }

  if (!existsSync(OUT_DIR)) mkdirSync(OUT_DIR, { recursive: true });

  console.log(`▶ Capturing ${DURATION_MS / 1000}s demo of "${TEMPLATE}"`);
  console.log(`  Frontend: ${FRONTEND_URL}`);
  console.log(`  Backend:  ${API_URL}`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    recordVideo: {
      dir: OUT_DIR,
      size: { width: 1440, height: 900 },
    },
  });
  const page = await context.newPage();

  // 1) Open dashboard
  await page.goto(FRONTEND_URL, { waitUntil: "networkidle" });

  // 2) Pick the template (button text matches `card-title`)
  await page.getByRole("button", { name: new RegExp(TEMPLATE, "i") }).click();

  // 3) Click ▶ Run
  await page.getByRole("button", { name: /^▶ Run$/i }).click();

  // 4) Wait for navigation to /runs/<id>
  await page.waitForURL(/\/runs\/[a-z0-9-]+/i, { timeout: 10_000 });

  // 5) Record the configured window
  await page.waitForTimeout(DURATION_MS);

  // 6) Tear down + rename the recorded file.
  const video = await page.video();
  await context.close();
  await browser.close();

  if (video) {
    const tmpPath = await video.path();
    const targetPath = FORMAT === "gif" ? OUT_PATH_GIF : OUT_PATH_MP4;
    if (FORMAT === "mp4") {
      await renameAsync(tmpPath, targetPath);
      console.log(`✓ wrote ${targetPath}`);
      return;
    }
    // gif path: convert via gifski
    const { spawnSync } = await import("node:child_process");
    const proc = spawnSync(
      "gifski",
      ["--quality", "85", "--fps", "20", "--output", OUT_PATH_GIF, tmpPath],
      { stdio: "inherit" },
    );
    if (proc.status !== 0) {
      console.error(
        "gifski failed. Install with `brew install gifski` or `cargo install gifski`. " +
          "MP4 saved to " +
          tmpPath,
      );
      process.exit(2);
    }
    console.log(`✓ wrote ${OUT_PATH_GIF}`);
  }
}

async function renameAsync(from, to) {
  const fs = await import("node:fs/promises");
  await fs.rename(from, to);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
