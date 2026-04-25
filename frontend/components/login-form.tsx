"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ApiClient } from "@/lib/api-client";
import { login } from "@/lib/auth";

interface LoginFormProps {
  next: string;
}

export function LoginForm({ next }: LoginFormProps): JSX.Element {
  const router = useRouter();
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
