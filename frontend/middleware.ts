/**
 * Optional auth gate. Runs only in Node mode (Next dev / next start /
 * Vercel) — static exports skip middleware entirely, in which case
 * the backend's own dependency does the gating.
 *
 * Strategy: when `NEXT_PUBLIC_AUTH_REQUIRED` is "true", redirect
 * unauthenticated users to `/login`. Authentication is detected by
 * the backend's HttpOnly session cookie. We can't read that cookie
 * directly because it's set by the backend (different host in dev),
 * so we accept any non-empty value of the local `__orchestra_authed`
 * cookie that the login page sets after a successful POST.
 *
 * When the env var is unset / "false", this is a no-op — every page
 * renders without an auth check.
 */

import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PATHS = new Set<string>([
  "/login",
  "/login/",
]);

function authRequired(): boolean {
  return process.env.NEXT_PUBLIC_AUTH_REQUIRED === "true";
}

export function middleware(req: NextRequest): NextResponse {
  if (!authRequired()) return NextResponse.next();

  // Static assets + Next.js internals never gate. The matcher below
  // already excludes most of these, but the login page assets are
  // the obvious exception.
  if (PUBLIC_PATHS.has(req.nextUrl.pathname)) return NextResponse.next();

  const sessionMarker = req.cookies.get("__orchestra_authed")?.value;
  if (sessionMarker === "1") return NextResponse.next();

  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.searchParams.set("next", req.nextUrl.pathname + req.nextUrl.search);
  return NextResponse.redirect(url);
}

export const config = {
  // Run on every page route except Next internals + the public assets.
  matcher: ["/((?!_next/|api/|favicon.ico|robots.txt|sitemap.xml).*)"],
};
