"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import useSWR from "swr";

import { DebateStream } from "@/components/debate-stream";
import { FinalOutputPanel } from "@/components/final-output-panel";
import { LucasPanel } from "@/components/lucas-panel";
import { RunHeader } from "@/components/run-header";
import { SkeletonLanes } from "@/components/skeleton-lanes";
import { Button } from "@/components/ui/button";
import { TooltipProvider } from "@/components/ui/tooltip";
import { api } from "@/lib/api-client";
import { useBatchedEvents } from "@/lib/use-batched-events";
import { useRunStream } from "@/lib/use-run-stream";
import { useStreamModel } from "@/lib/use-stream-model";
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
  const { events: liveEvents, status, terminal, error: wsError, reconnect } =
    useRunStream(runId);
  const events = useBatchedEvents(liveEvents);
  const model = useStreamModel(events);
  const [lucasOpenMobile, setLucasOpenMobile] = useState(false);

  // Auto-open the Lucas drawer the first time he speaks on mobile, so a
  // veto isn't hidden behind a toggle on the small-screen layout.
  useEffect(() => {
    if (model.lucas.status === "vetoed") setLucasOpenMobile(true);
  }, [model.lucas.status]);

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

  // Prefer the terminal frame's final_output (it's the source of truth
  // emitted exactly once); fall back to the run snapshot.
  const finalText =
    model.finalOutput ??
    (terminal?.type === "run_completed" && typeof terminal.final_output === "string"
      ? terminal.final_output
      : null) ??
    run?.final_output ??
    null;

  const noEventsYet = events.length === 0;

  return (
    <TooltipProvider delayDuration={200}>
      <div className="space-y-6">
        <RunHeader
          runId={runId}
          run={run}
          status={status}
          round={model.round}
          onReplay={reconnect}
        />

        {wsError ? (
          <p
            role="alert"
            className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive"
          >
            Stream error: {wsError.message}. Falling back to polling — click
            replay to reconnect.
          </p>
        ) : null}

        {/* Desktop courtroom layout: lanes on the left (3 cols), Lucas on the right */}
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="min-w-0 space-y-3">
            {noEventsYet && status !== "errored" ? (
              <SkeletonLanes />
            ) : (
              <DebateStream model={model} />
            )}
          </div>

          {/* Desktop Lucas panel — sticky so it tracks the page scroll. */}
          <div className="hidden lg:block">
            <div className="sticky top-20 max-h-[calc(100vh-6rem)]">
              <LucasPanel state={model.lucas} className="max-h-[calc(100vh-6rem)]" />
            </div>
          </div>
        </div>

        <FinalOutputPanel
          runId={runId}
          text={finalText}
          failureReason={model.failureReason}
        />

        {/* Mobile Lucas drawer — sticky bottom, expands on tap. */}
        <div className="lg:hidden">
          <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background/95 shadow-2xl backdrop-blur">
            <button
              type="button"
              className="flex w-full items-center justify-between px-4 py-2 text-sm"
              onClick={() => setLucasOpenMobile((v) => !v)}
              aria-expanded={lucasOpenMobile}
              aria-controls="lucas-drawer"
            >
              <span className="font-semibold">
                Lucas {model.lucas.status !== "idle" ? `· ${model.lucas.status}` : ""}
              </span>
              <span aria-hidden>{lucasOpenMobile ? "▾" : "▴"}</span>
            </button>
            <div
              id="lucas-drawer"
              hidden={!lucasOpenMobile}
              className="max-h-[60vh] overflow-y-auto"
            >
              <LucasPanel state={model.lucas} className="border-0 shadow-none" />
            </div>
          </div>
          {/* Spacer so content isn't hidden under the drawer collapsed bar. */}
          <div className="h-12" aria-hidden />
        </div>
      </div>
    </TooltipProvider>
  );
}
