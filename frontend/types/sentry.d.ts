// Ambient declaration for the optional `@sentry/nextjs` runtime dep.
// We never list it in `package.json` — users only install it when they
// configure a DSN. The dynamic import in `lib/sentry.ts` falls back to
// `null` when the package is missing, so this declaration only needs to
// describe the surface we actually call.
declare module "@sentry/nextjs" {
  export function init(opts: unknown): void;
  export function captureException(e: unknown): void;
}
