"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const STORAGE_KEY = "grok-orchestra:api-base-url";

export function SettingsForm(): JSX.Element {
  const [value, setValue] = useState<string>("");
  const [saved, setSaved] = useState<boolean>(false);

  useEffect(() => {
    const stored =
      typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
    setValue(stored ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");
  }, []);

  function onSubmit(e: React.FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    if (typeof window !== "undefined") {
      if (value.trim()) localStorage.setItem(STORAGE_KEY, value.trim());
      else localStorage.removeItem(STORAGE_KEY);
    }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>API base URL</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <input
            type="url"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            placeholder="http://localhost:8000"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Stored in <code className="font-mono">localStorage</code>. Used by
            this browser only. Reload after saving.
          </p>
          <div className="flex items-center gap-3">
            <Button type="submit">Save</Button>
            {saved ? (
              <span className="text-xs text-muted-foreground">✓ saved</span>
            ) : null}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
