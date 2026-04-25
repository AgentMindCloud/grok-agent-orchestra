"use client";

import {
  CheckCircle2,
  CircleDot,
  Database,
  FileSearch,
  Globe,
  Loader2,
  Plug,
  TriangleAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import type { ToolCall } from "@/lib/use-stream-model";
import { cn } from "@/lib/utils";

interface RoleToolCallProps {
  call: ToolCall;
  className?: string;
}

function iconFor(toolName: string): typeof Globe {
  const t = toolName.toLowerCase();
  if (t.includes("web") || t.includes("search") || t.includes("fetch")) return Globe;
  if (t.includes("file") || t.includes("local") || t.includes("doc")) return FileSearch;
  if (t.includes("sql") || t.includes("postgres") || t.includes("query")) return Database;
  if (t.includes("mcp") || t.includes("__")) return Plug;
  return CircleDot;
}

const STATUS_TONE = {
  calling: "border-amber-500/40 bg-amber-500/5",
  ok: "border-emerald-500/40 bg-emerald-500/5",
  error: "border-destructive/40 bg-destructive/5",
} as const;

export function RoleToolCall({ call, className }: RoleToolCallProps): JSX.Element {
  const Icon = iconFor(call.toolName);
  const argsPreview =
    typeof call.args === "string"
      ? call.args
      : JSON.stringify(call.args ?? {}, null, 2);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "group flex w-full items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-xs transition-colors hover:border-primary/40 hover:bg-primary/5",
            STATUS_TONE[call.status],
            className,
          )}
          aria-label={`${call.toolName} (${call.status})`}
        >
          <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
          <span className="truncate font-mono text-[11px] font-medium">
            {call.toolName}
          </span>
          <span className="ml-auto inline-flex items-center gap-1">
            {call.status === "calling" ? (
              <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" aria-hidden />
            ) : call.status === "ok" ? (
              <CheckCircle2 className="h-3 w-3 text-emerald-500" aria-hidden />
            ) : (
              <TriangleAlert className="h-3 w-3 text-destructive" aria-hidden />
            )}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-96 max-w-[90vw] space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4" aria-hidden />
            <code className="font-mono text-sm">{call.toolName}</code>
          </div>
          <Badge variant="outline" className="text-[10px] uppercase">
            {call.status}
          </Badge>
        </div>
        <div>
          <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Arguments
          </p>
          <pre className="max-h-40 overflow-auto rounded bg-muted/40 p-2 font-mono text-[11px] leading-relaxed">
            {argsPreview}
          </pre>
        </div>
        {call.result ? (
          <div>
            <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Result
            </p>
            <pre className="max-h-56 overflow-auto rounded bg-muted/40 p-2 font-mono text-[11px] leading-relaxed">
              {call.result}
            </pre>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
