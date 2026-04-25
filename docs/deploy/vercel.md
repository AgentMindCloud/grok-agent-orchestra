# Vercel — frontend only

The Next.js dashboard deploys to [Vercel](https://vercel.com) cleanly.
The FastAPI backend cannot run on Vercel (long-lived WebSockets +
multi-thread runner aren&rsquo;t a fit) — host it separately on Render,
Fly.io, or Docker (see [Docker](docker.md)) and point the frontend at
its public URL.

## One-time setup

1. Push the repo to GitHub.
2. Import the project at <https://vercel.com/new>.
3. **Root directory**: `frontend` (so Vercel only builds the JS package).
4. **Framework preset**: Next.js (auto-detected via `vercel.json`).
5. **Environment variables** (Production + Preview):

    | Var | Value | Notes |
    | --- | --- | --- |
    | `NEXT_PUBLIC_API_URL` | `https://api.example.com` | The public origin of your FastAPI backend. |
    | `NEXT_PUBLIC_WS_URL`  | `wss://api.example.com`  | WebSocket origin. Defaults to `NEXT_PUBLIC_API_URL` with the protocol swapped. |
    | `NEXT_PUBLIC_SITE_URL` | `https://app.example.com` | Used for canonical links + Open Graph tags. |
    | `NEXT_PUBLIC_AUTH_REQUIRED` | `true` | Set when the backend has `GROK_ORCHESTRA_AUTH_PASSWORD` set. |
    | `NEXT_PUBLIC_SENTRY_DSN` | *(optional)* | Enables Sentry on the frontend bundle. |

6. **Backend CORS**: on the FastAPI side, add the Vercel deployment URL to
   `GROK_ORCHESTRA_CORS_ORIGINS` (comma-separated) so the browser can
   reach the API.

## Auth

`/login` is a public path; everything else is gated by the Next.js
middleware when `NEXT_PUBLIC_AUTH_REQUIRED=true`. Set the matching
`GROK_ORCHESTRA_AUTH_PASSWORD` on the **backend** so both layers
agree. See [`docs/contributing/index.md`](../contributing/index.md) for
the full threat model.

## Preview deploys

Every PR gets its own preview at `https://<branch>.<vercel-project>.vercel.app`.
That URL needs to also be added to the backend&rsquo;s
`GROK_ORCHESTRA_CORS_ORIGINS` allowlist — Vercel doesn&rsquo;t proxy back to
your FastAPI process.

## Custom domain

Add the domain in Vercel and update both:

- `NEXT_PUBLIC_SITE_URL` → matches the new domain.
- Backend `GROK_ORCHESTRA_CORS_ORIGINS` → adds the new origin.

## See also

- [Docker](docker.md) — single-process self-host (frontend baked into the
  backend image).
- [Render](render.md) — managed backend that pairs nicely with a Vercel
  frontend.
- [Fly.io](fly.md) — global-edge backend.
