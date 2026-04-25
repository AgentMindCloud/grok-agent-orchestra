"use client";

import Link from "next/link";
import useSWR from "swr";

import { DebateStream } from "@/components/debate-stream";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { ApiClient, api } from "@/lib/api-client";
import { useRunStream } from "@/lib/use-run-stream";
import type { RunDetail } from "@/types/api";

interface RunDetailViewProps {
  runId: string;
}

const fetcher = async (key: string): Promise<RunDetail> => {
  const id = key.split("/").pop() as string;
  return api.getRun(id);
};

export function RunDetailView({ runId }: RunDetailViewProps): JSX.Element {
  const { data: run, error } = useSWR<RunDetail>(`/api/runs/${runId}`, fetcher, {
    refreshInterval: 4000,
  });
  const { events, status, terminal, error: wsError } = useRunStream(runId);

  if (error) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">Run not found</h1>
        <p className="text-muted-foreground">
          {error instanceof Error ? error.message : String(error)}
        </p>
        <Button asChild variant="outline">
          <Link href="/">Back to dashboard</Link>
        </Button>
      </div>
    );
  }

  const finalOutput =
    (terminal?.type === "run_completed" &&
      typeof terminal.final_output === "string" &&
      terminal.final_output) ||
    run?.final_output ||
    "";
  const veto = run?.veto_report ?? null;
  const apiClient = new ApiClient();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {run?.template_name ?? "Run"}
          </h1>
          <p className="font-mono text-xs text-muted-foreground">{runId}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={run?.simulated ? "secondary" : "default"}>
            {run?.simulated ? "simulated" : "live"}
          </Badge>
          <Badge variant="outline">{status}</Badge>
          {run?.status ? <Badge>{run.status}</Badge> : null}
        </div>
      </div>

      {wsError ? (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          Stream error: {wsError.message}. Falling back to polling.
        </p>
      ) : null}

      <DebateStream events={events} />

      <Separator />

      <section className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Final output</CardTitle>
          </CardHeader>
          <CardContent>
            {finalOutput ? (
              <pre className="whitespace-pre-wrap break-words font-mono text-sm leading-relaxed">
                {finalOutput}
              </pre>
            ) : (
              <p className="text-sm text-muted-foreground">
                Pending — Lucas hasn&rsquo;t signed off yet.
              </p>
            )}
            {finalOutput ? (
              <div className="mt-4 flex flex-wrap gap-2">
                <Button asChild variant="outline" size="sm">
                  <a href={apiClient.reportUrl(runId, "md")} target="_blank" rel="noreferrer">
                    Download .md
                  </a>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <a href={apiClient.reportUrl(runId, "pdf")} target="_blank" rel="noreferrer">
                    Download .pdf
                  </a>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <a href={apiClient.reportUrl(runId, "docx")} target="_blank" rel="noreferrer">
                    Download .docx
                  </a>
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Lucas verdict</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {veto ? (
              <>
                <p>
                  <span className="font-medium">
                    {veto.approved ? "✅ Approved" : "❌ Vetoed"}
                  </span>
                  {typeof veto.confidence === "number" ? (
                    <span className="ml-2 font-mono text-xs text-muted-foreground">
                      conf {veto.confidence.toFixed(2)}
                    </span>
                  ) : null}
                </p>
                {veto.reasons && veto.reasons.length > 0 ? (
                  <ul className="list-disc pl-4 text-muted-foreground">
                    {veto.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                ) : null}
              </>
            ) : (
              <p className="text-muted-foreground">
                Pending — verdict lands when the run completes.
              </p>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
