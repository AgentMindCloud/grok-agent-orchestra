"use client";

import {
  CircleDashed,
  Clock,
  Cpu,
  Coins,
  Gauge,
  RotateCw,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { StreamConnectionStatus } from "@/lib/use-run-stream";
import type { RunDetail } from "@/types/api";
import { cn } from "@/lib/utils";

interface RunHeaderProps {
  runId: string;
  run: RunDetail | undefined;
  status: StreamConnectionStatus;
  round: number;
  onReplay?: () => void;
}

function durationOf(run: RunDetail | undefined): string {
  if (!run?.started_at) return "—";
  const end = run.completed_at ?? new Date().toISOString();
  const ms = new Date(end).getTime() - new Date(run.started_at).getTime();
  if (Number.isNaN(ms) || ms < 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

function costOf(run: RunDetail | undefined): string {
  if (!run) return "—";
  // Surfaced as `usage.cost_usd` by the backend's run snapshot when
  // the cost field is populated; in simulated runs it stays at 0.
  const usage = (run as unknown as { usage?: Record<string, unknown> }).usage;
  const raw = usage && typeof usage === "object" ? usage["cost_usd"] : undefined;
  const v = typeof raw === "number" ? raw : 0;
  return v > 0 ? `$${v.toFixed(3)}` : "$0.00";
}

const STATUS_TONE: Record<StreamConnectionStatus, string> = {
  idle: "text-muted-foreground",
  connecting: "text-amber-500",
  open: "text-emerald-500",
  closed: "text-muted-foreground",
  reconnecting: "text-amber-500",
  errored: "text-destructive",
};

export function RunHeader({
  runId,
  run,
  status,
  round,
  onReplay,
}: RunHeaderProps): JSX.Element {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4 rounded-lg border bg-card/40 p-4 shadow-sm">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h1 className="truncate text-xl font-semibold tracking-tight">
            {run?.template_name ?? "Run"}
          </h1>
          {run ? (
            <Badge variant={run.simulated ? "secondary" : "default"}>
              {run.simulated ? "simulated" : "live"}
            </Badge>
          ) : null}
          {run ? <Badge>{run.status}</Badge> : null}
          <Badge variant="outline" className={cn("font-mono text-[11px]", STATUS_TONE[status])}>
            <CircleDashed className="mr-1 h-3 w-3" aria-hidden /> {status}
          </Badge>
        </div>
        <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground">
          {runId}
        </p>
      </div>

      <dl className="grid grid-flow-col gap-x-4 gap-y-1 text-xs">
        <Stat icon={<Cpu className="h-3.5 w-3.5" aria-hidden />} label="Round">
          {round > 0 ? round : "—"}
        </Stat>
        <Stat icon={<Clock className="h-3.5 w-3.5" aria-hidden />} label="Duration">
          {durationOf(run)}
        </Stat>
        <Stat icon={<Coins className="h-3.5 w-3.5" aria-hidden />} label="Cost">
          {costOf(run)}
        </Stat>
        <Stat icon={<Gauge className="h-3.5 w-3.5" aria-hidden />} label="Mode">
          {run?.simulated ? "sim" : "live"}
        </Stat>
      </dl>

      {onReplay && run?.status === "completed" ? (
        <Button variant="outline" size="sm" onClick={onReplay}>
          <RotateCw className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Replay
        </Button>
      ) : null}
    </header>
  );
}

function Stat({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-muted-foreground">{icon}</span>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono font-medium">{children}</dd>
    </div>
  );
}
