"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ApiClient } from "@/lib/api-client";
import { login } from "@/lib/auth";

// `useSearchParams()` reads `?next=…` on the client, so the parent
// page stays statically renderable for the export target.
function LoginFormInner(): JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams?.get("next") ?? "/";
  const [pwd, setPwd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    if (!pwd) return;
    setBusy(true);
    setError(null);
    try {
      const client = new ApiClient();
      await login(client, pwd);
      // Cookie marker for the Next.js middleware (the real session
      // cookie is HttpOnly + set by the backend; we mirror a lightweight
      // marker here so the edge redirect knows the user is in).
      document.cookie =
        "__orchestra_authed=1; Path=/; Max-Age=86400; SameSite=Lax";
      const target = next && next.startsWith("/") ? next : "/";
      router.push(target);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Sign in</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Password</span>
            <input
              autoFocus
              type="password"
              autoComplete="current-password"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              value={pwd}
              onChange={(e) => setPwd(e.target.value)}
            />
          </label>
          {error ? (
            <p role="alert" className="text-xs text-destructive">
              {error}
            </p>
          ) : null}
          <Button type="submit" disabled={busy || !pwd} className="w-full">
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// `useSearchParams()` needs a Suspense boundary above it during static
// pre-render or Next bails the page out of static generation. The
// fallback shows the empty card so layout shifts stay invisible while
// the inner component reads the URL on hydration.
export function LoginForm(): JSX.Element {
  return (
    <Suspense
      fallback={
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Sign in</CardTitle>
          </CardHeader>
          <CardContent />
        </Card>
      }
    >
      <LoginFormInner />
    </Suspense>
  );
}
