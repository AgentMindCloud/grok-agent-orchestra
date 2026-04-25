"use client";

import useSWR from "swr";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import {
  setSelectedTemplate,
  useSelectedTemplate,
} from "@/lib/selection-store";
import { cn } from "@/lib/utils";
import type { TemplatesListResponse } from "@/types/api";

const fetcher = async (): Promise<TemplatesListResponse> => api.listTemplates();

export function TemplatePicker(): JSX.Element {
  const { data, error, isLoading } = useSWR<TemplatesListResponse>(
    "/api/templates",
    fetcher,
  );
  const active = useSelectedTemplate();

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Templates failed to load</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            {error instanceof Error ? error.message : String(error)}
          </p>
          <p className="mt-2 text-xs">
            Check that the backend is reachable at{" "}
            <code className="font-mono">
              {process.env.NEXT_PUBLIC_API_URL ?? "/api"}
            </code>
            .
          </p>
        </CardContent>
      </Card>
    );
  }

  if (isLoading || !data) {
    return <div className="h-64 animate-pulse rounded-md bg-muted" />;
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {data.templates.map((tpl) => (
        <button
          key={tpl.name}
          type="button"
          onClick={() => setSelectedTemplate(tpl.name)}
          className={cn(
            "rounded-lg border bg-card p-4 text-left transition hover:-translate-y-0.5 hover:border-primary/50",
            active === tpl.name && "border-primary ring-2 ring-primary/20",
          )}
        >
          <div className="flex items-start justify-between gap-3">
            <h3 className="font-medium">{tpl.name}</h3>
            <Badge variant="secondary">{tpl.category}</Badge>
          </div>
          <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
            {tpl.description}
          </p>
          <div className="mt-3 flex flex-wrap gap-1">
            {tpl.tags.slice(0, 4).map((t) => (
              <span
                key={t}
                className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
              >
                {t}
              </span>
            ))}
          </div>
        </button>
      ))}
    </div>
  );
}
