"use client";

import Link from "next/link";
import useSWR from "swr";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import type { RunsListResponse, RunStatus } from "@/types/api";

const fetcher = async (): Promise<RunsListResponse> => api.listRuns();

const STATUS_VARIANT: Record<RunStatus, "default" | "secondary" | "destructive" | "outline"> = {
  pending: "outline",
  running: "default",
  completed: "secondary",
  failed: "destructive",
};

export function RecentRuns(): JSX.Element {
  const { data, error, isLoading } = useSWR<RunsListResponse>(
    "/api/runs",
    fetcher,
    { refreshInterval: 4000 },
  );

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle>Recent runs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {error ? (
          <p className="text-sm text-destructive">
            {error instanceof Error ? error.message : String(error)}
          </p>
        ) : isLoading || !data ? (
          <div className="h-24 animate-pulse rounded-md bg-muted" />
        ) : data.runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No runs yet. Pick a template and hit <kbd>▶ Run</kbd>.
          </p>
        ) : (
          data.runs.slice(0, 8).map((run) => (
            <Link
              key={run.id}
              href={`/runs/${run.id}`}
              className="flex items-center justify-between rounded-md border bg-card px-3 py-2 text-sm transition-colors hover:bg-muted"
            >
              <span className="truncate pr-3 font-mono text-xs">
                {run.template_name ?? run.id.slice(0, 8)}
              </span>
              <Badge variant={STATUS_VARIANT[run.status] ?? "outline"}>
                {run.status}
              </Badge>
            </Link>
          ))
        )}
      </CardContent>
    </Card>
  );
}
