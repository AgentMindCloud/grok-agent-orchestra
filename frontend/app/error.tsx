"use client";

import { AlertOctagon, RotateCw } from "lucide-react";
import { useEffect } from "react";

import { Button } from "@/components/ui/button";

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ErrorPage({ error, reset }: ErrorPageProps): JSX.Element {
  useEffect(() => {
    // Hand the error to Sentry if it's loaded; otherwise log to the
    // browser console so devs see it during development.
    void import("@/lib/sentry").then(({ captureException }) => {
      captureException(error);
    });
    // eslint-disable-next-line no-console
    console.error("[orchestra] route error:", error);
  }, [error]);

  return (
    <div className="mx-auto flex min-h-[50vh] max-w-md flex-col items-center justify-center gap-4 text-center">
      <span className="rounded-full bg-destructive/10 p-3 text-destructive">
        <AlertOctagon className="h-7 w-7" aria-hidden />
      </span>
      <div className="space-y-1.5">
        <h1 className="text-xl font-semibold tracking-tight">Something broke.</h1>
        <p className="text-sm text-muted-foreground">
          {error.message || "An unexpected error occurred while rendering this page."}
        </p>
        {error.digest ? (
          <p className="font-mono text-[10px] text-muted-foreground">
            digest: {error.digest}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <Button onClick={reset}>
          <RotateCw className="mr-1.5 h-3.5 w-3.5" /> Try again
        </Button>
        <Button asChild variant="outline">
          <a href="/">Back to dashboard</a>
        </Button>
      </div>
    </div>
  );
}
