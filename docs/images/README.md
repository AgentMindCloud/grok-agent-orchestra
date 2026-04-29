# docs/images

Branded SVG illustrations referenced from the top-level `README.md`
and the docs site. They are **illustrations, not screenshots** — each
file's `<desc>` element says so for screen readers and search engines.

## Inventory

- `hero.svg` — top-of-README hero. Four role dots + wordmark + tagline.
- `tui-demo.svg` — Rich-style four-lane terminal mockup with a Lucas
  verdict bar.
- `web-ui.svg` — classic Next.js dashboard mockup (sidebar + lanes +
  verdict card).
- `web-ui-modern.svg` — courtroom view (raised Lucas bench + three
  speaker lanes).
- `report-sample.svg` — A4-ratio mockup of a generated report PDF.
- `trace-langsmith.svg` — span-tree mockup as it appears in a
  tracing backend.

## Why illustrations and not screenshots

A real screenshot of the dashboard or TUI requires a live stack with
real API keys and a finished run. Until that pipeline is automated by
`scripts/capture-demo.mjs` (post-launch), shipping fake or stale
PNGs would mislead readers. Illustrations are honest.

## Replacing with real screenshots later

When `scripts/capture-demo.mjs` lands:

1. Run it against a live stack with real keys.
2. Drop the captured PNG/GIF next to the corresponding SVG with the
   same base name (e.g. `tui-demo.png`).
3. Update the `README.md` reference from `.svg` → `.png` (or `.gif`
   for animated TUI / web demos).
4. Keep the SVGs around as a fallback for the docs site, where the
   raster files would inflate the build.

Keep individual rasters under ~3 MB so the GitHub README loads
without spinners. Prefer GIF/PNG over MP4 — GitHub renders the
former inline.
