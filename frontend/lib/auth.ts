/**
 * Frontend auth glue — talks to the backend's `/api/auth/*` endpoints.
 *
 * Auth is OFF by default. The backend's `/api/auth/status` is the
 * single source of truth: when it reports `required: false`, the
 * middleware short-circuits and no UI ever mentions auth.
 */

import type { ApiClient } from "@/lib/api-client";

export interface AuthStatus {
  required: boolean;
  authenticated: boolean;
}

export interface LoginResult {
  required: boolean;
  authenticated: boolean;
}

const COOKIE_NAME = "__orchestra_session";

/**
 * GET /api/auth/status — used by middleware + the login page itself.
 * Tolerates a 404 (older backend) by falling back to "auth disabled".
 */
export async function fetchAuthStatus(
  client: ApiClient,
): Promise<AuthStatus> {
  try {
    // The endpoint isn't in `ApiClient` because it's not part of the
    // typed surface — auth is a meta-concern. Hit the URL directly.
    const base = (client as unknown as { base: string }).base ?? "";
    const res = await fetch(`${base}/api/auth/status`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) return { required: false, authenticated: true };
    return (await res.json()) as AuthStatus;
  } catch {
    return { required: false, authenticated: true };
  }
}

export async function login(
  client: ApiClient,
  password: string,
): Promise<LoginResult> {
  const base = (client as unknown as { base: string }).base ?? "";
  const res = await fetch(`${base}/api/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    let detail = "login failed";
    try {
      const blob = await res.json();
      if (typeof blob.detail === "string") detail = blob.detail;
    } catch {
      /* swallow */
    }
    throw new Error(detail);
  }
  return (await res.json()) as LoginResult;
}

export async function logout(client: ApiClient): Promise<void> {
  const base = (client as unknown as { base: string }).base ?? "";
  await fetch(`${base}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export { COOKIE_NAME };
