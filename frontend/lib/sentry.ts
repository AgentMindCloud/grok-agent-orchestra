/**
 * Optional Sentry hook. Loads only when both env vars are set:
 *
 *   NEXT_PUBLIC_SENTRY_DSN=https://...@o0.ingest.sentry.io/0
 *   NEXT_PUBLIC_SENTRY_ENVIRONMENT=production
 *
 * Without those vars, `captureException` is a no-op and `@sentry/nextjs`
 * never enters the bundle. That keeps Sentry truly optional — neither
 * the install nor the runtime cost lands on users who didn't ask for it.
 *
 * The dynamic import is wrapped in a try/catch so that a missing
 * `@sentry/nextjs` dependency in `node_modules` (the most common case
 * when Sentry isn't wanted) is silently ignored.
 */

type SentryAPI = {
  captureException: (e: unknown) => void;
};

let cached: SentryAPI | null = null;

async function load(): Promise<SentryAPI | null> {
  if (cached) return cached;
  if (typeof window === "undefined") return null;
  const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
  if (!dsn) return null;
  try {
    // `@sentry/nextjs` is an optional runtime dep — never installed by
    // default, only loaded if a DSN is configured. Type declarations live
    // alongside this file in `sentry.d.ts` so the dynamic import stays
    // typed without forcing the package into the dependency tree.
    const Sentry = (await import(/* @vite-ignore */ "@sentry/nextjs").catch(
      () => null,
    )) as { init?: (opts: unknown) => void; captureException?: (e: unknown) => void } | null;
    if (!Sentry || typeof Sentry.init !== "function") return null;
    Sentry.init({
      dsn,
      environment:
        process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "production",
      tracesSampleRate: 0.1,
      replaysOnErrorSampleRate: 1.0,
      replaysSessionSampleRate: 0,
    });
    cached = {
      captureException: (e) => Sentry.captureException?.(e),
    };
    return cached;
  } catch {
    return null;
  }
}

export async function captureException(e: unknown): Promise<void> {
  const api = await load();
  if (!api) return;
  api.captureException(e);
}
