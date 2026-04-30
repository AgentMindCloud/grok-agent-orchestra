"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2,
  Eye,
  Gavel,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useRef } from "react";

import { RoleAvatar } from "@/components/role-avatar";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { roleMeta } from "@/lib/role-meta";
import type { LucasState } from "@/lib/use-stream-model";
import { cn } from "@/lib/utils";

interface LucasPanelProps {
  state: LucasState;
  className?: string;
}

const STATUS_LABEL: Record<LucasState["status"], string> = {
  idle: "Stand-by",
  observing: "Observing",
  passed: "Passed",
  vetoed: "Vetoed",
};

const STATUS_TONE: Record<LucasState["status"], string> = {
  idle: "text-muted-foreground",
  observing: "text-amber-500",
  passed: "text-emerald-500",
  vetoed: "text-destructive",
};

function StatusIcon({ status }: { status: LucasState["status"] }): JSX.Element {
  if (status === "vetoed") return <Gavel className="h-4 w-4" aria-hidden />;
  if (status === "passed") return <CheckCircle2 className="h-4 w-4" aria-hidden />;
  if (status === "observing") return <Eye className="h-4 w-4 animate-pulse motion-reduce:animate-none" aria-hidden />;
  return <ShieldAlert className="h-4 w-4" aria-hidden />;
}

export function LucasPanel({ state, className }: LucasPanelProps): JSX.Element {
  const meta = roleMeta("Lucas");
  const lastVerdictId = state.verdicts.at(-1)?.id ?? null;
  const liveRegionRef = useRef<HTMLDivElement>(null);

  // Announce vetoes to assistive tech via a polite live region.
  // Depending on `state.verdicts` would re-fire on every push (each new
  // event mutates the array), re-announcing the same verdict. Keying on
  // `lastVerdictId` is the intended behaviour.
  useEffect(() => {
    if (!liveRegionRef.current) return;
    const last = state.verdicts.at(-1);
    if (!last) return;
    liveRegionRef.current.textContent =
      last.kind === "vetoed"
        ? `Lucas vetoed: ${last.reason ?? "no reason given"}`
        : `Lucas approved with confidence ${last.confidence?.toFixed(2) ?? "n/a"}.`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastVerdictId]);

  const conf = state.confidence ?? 0;
  const confPct = Math.round(conf * 100);

  return (
    <aside
      className={cn(
        "flex h-full flex-col rounded-lg border bg-gradient-to-br from-background via-background to-role-lucas/5 shadow-sm",
        meta.borderClass,
        className,
      )}
      aria-label="Lucas judge bench"
    >
      <header className="flex items-center justify-between gap-3 border-b border-border/60 p-3">
        <div className="flex items-center gap-2.5">
          <RoleAvatar role="Lucas" size="lg" active={state.status !== "idle"} />
          <div>
            <p className={cn("text-sm font-semibold", meta.textClass)}>Lucas</p>
            <p className="text-[11px] text-muted-foreground">Safety judge</p>
          </div>
        </div>
        <Badge
          variant="outline"
          className={cn(
            "inline-flex items-center gap-1 text-[11px] uppercase",
            STATUS_TONE[state.status],
          )}
        >
          <StatusIcon status={state.status} />
          {STATUS_LABEL[state.status]}
        </Badge>
      </header>

      <div
        ref={liveRegionRef}
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      />

      <div className="space-y-1 border-b border-border/60 px-3 py-2.5">
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>Confidence</span>
          <span className="font-mono">{state.confidence === null ? "—" : `${confPct}%`}</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
          <motion.div
            className={cn(
              "h-full",
              state.status === "vetoed"
                ? "bg-destructive"
                : "bg-gradient-to-r from-role-lucas via-amber-500 to-emerald-500",
            )}
            animate={{ width: `${state.confidence === null ? 0 : confPct}%` }}
            transition={{ duration: 0.4, ease: "easeOut" }}
          />
        </div>
      </div>

      <ScrollArea className="flex-1">
        <ol className="flex max-h-[60vh] flex-col gap-2 overflow-y-auto p-3">
          {state.verdicts.length === 0 ? (
            <li className="my-auto text-center text-xs italic text-muted-foreground">
              Lucas hasn&rsquo;t said a word yet.
            </li>
          ) : (
            <AnimatePresence initial={false}>
              {state.verdicts
                .slice()
                .reverse()
                .map((v) => (
                  <motion.li
                    key={v.id}
                    layout
                    initial={{ opacity: 0, x: 12 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.18 }}
                    className={cn(
                      "rounded-md border p-2.5 text-xs",
                      v.kind === "vetoed"
                        ? "border-destructive/50 bg-destructive/5"
                        : "border-emerald-500/40 bg-emerald-500/5",
                    )}
                  >
                    {v.kind === "vetoed" ? (
                      <div className="space-y-1.5">
                        <div className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase text-destructive">
                          <Gavel className="h-3 w-3" aria-hidden /> vetoed
                        </div>
                        {v.reason ? (
                          <p className="text-foreground/90">{v.reason}</p>
                        ) : null}
                        {v.blockedContent ? (
                          <details className="mt-1">
                            <summary className="cursor-pointer text-[11px] text-muted-foreground">
                              Show blocked content
                            </summary>
                            <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted/40 p-2 font-mono text-[10px] leading-snug">
                              {v.blockedContent}
                            </pre>
                          </details>
                        ) : null}
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-2">
                        <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase text-emerald-600 dark:text-emerald-400">
                          <CheckCircle2 className="h-3 w-3" aria-hidden /> passed
                        </span>
                        {typeof v.confidence === "number" ? (
                          <span className="font-mono text-[11px] text-muted-foreground">
                            conf {v.confidence.toFixed(2)}
                          </span>
                        ) : null}
                      </div>
                    )}
                  </motion.li>
                ))}
            </AnimatePresence>
          )}
        </ol>
      </ScrollArea>
    </aside>
  );
}
