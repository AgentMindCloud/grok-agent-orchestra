# Agent Orchestra — frontend

Next.js 14 (App Router) + Tailwind + shadcn/ui dashboard for
`grok-agent-orchestra`. Reaches parity with the v1 single-file HTML
dashboard (which still ships at `/classic/` as a fallback). The
killer rich-debate visualisation lands in 16b.

## Dev

```bash
cd frontend
cp .env.example .env.local
pnpm install
pnpm dev          # http://localhost:3000
```

> **Note on the lockfile.** `pnpm-lock.yaml` is intentionally **not**
> checked in yet — this dir hasn't had its first contributor run on a
> known-clean environment. The first PR that runs `pnpm install` here
> should commit the resulting `pnpm-lock.yaml` so subsequent installs
> are deterministic. Don't ship a stub lockfile.

In a separate terminal, run the FastAPI backend:

```bash
grok-orchestra serve --no-browser    # http://localhost:8000
```

The backend ships CORS for `http://localhost:3000` out of the box. To
add additional origins, set:

```bash
export GROK_ORCHESTRA_CORS_ORIGINS="https://staging.example.com,https://prod.example.com"
```

## Build

```bash
pnpm build && pnpm start             # Node-served Next.js
NEXT_BUILD_TARGET=export pnpm build  # static export → out/ (Docker)
```

## Generate API types

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm generate:types
# writes types/api.generated.ts
```

The hand-written `types/api.ts` mirrors the backend shapes and is the
default. The generated types are an extra layer used when the backend
adds endpoints faster than the hand-written types catch up.

## Tests

```bash
pnpm test        # vitest run
pnpm typecheck   # tsc --noEmit
pnpm lint        # next lint
```

## Layout

```
frontend/
  app/
    layout.tsx
    page.tsx                       # dashboard
    runs/[runId]/page.tsx          # run detail + live stream
    templates/page.tsx
    settings/page.tsx
    globals.css
  components/
    header.tsx
    template-picker.tsx
    run-trigger.tsx
    debate-stream.tsx              # role-coloured lanes
    run-detail-view.tsx
    template-browser.tsx
    settings-form.tsx
    recent-runs.tsx
    theme-provider.tsx
    theme-toggle.tsx
    ui/                            # shadcn primitives (button, card, badge, separator)
  lib/
    api-client.ts                  # typed wrapper around fetch
    events.ts                      # event narrowers + role colour map
    use-run-stream.ts              # WS hook with reconnect + buffer
    selection-store.ts             # active-template state
    utils.ts                       # cn() helper
  types/
    api.ts                         # hand-written shapes
  __tests__/
    api-client.test.ts
    use-run-stream.test.ts
```
