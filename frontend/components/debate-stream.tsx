"use client";

import { useEffect, useMemo, useRef } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ROLE_TONE,
  isRoleCompleted,
  isRoleStarted,
  isStream,
  type RoleName,
} from "@/lib/events";
import { cn } from "@/lib/utils";
import type { WireEvent } from "@/types/api";

const ROLE_ORDER: RoleName[] = ["Grok", "Harper", "Benjamin", "Lucas"];

interface Bubble {
  id: string;
  role: RoleName;
  text: string;
  closed: boolean;
}

interface Lane {
  role: RoleName;
  bubbles: Bubble[];
}

function buildLanes(events: WireEvent[]): Lane[] {
  const lanes: Record<RoleName, Lane> = {
    Grok: { role: "Grok", bubbles: [] },
    Harper: { role: "Harper", bubbles: [] },
    Benjamin: { role: "Benjamin", bubbles: [] },
    Lucas: { role: "Lucas", bubbles: [] },
  };

  let openIds: Partial<Record<RoleName, string>> = {};

  for (const ev of events) {
    if (isRoleStarted(ev)) {
      const id = `${ev.role}-${ev.seq ?? lanes[ev.role].bubbles.length}`;
      lanes[ev.role].bubbles.push({
        id,
        role: ev.role,
        text: "",
        closed: false,
      });
      openIds[ev.role] = id;
      continue;
    }
    if (isRoleCompleted(ev)) {
      const id = openIds[ev.role];
      if (id) {
        const bubble = lanes[ev.role].bubbles.find((b) => b.id === id);
        if (bubble) {
          if (ev.output && ev.output.length > bubble.text.length) {
            bubble.text = ev.output;
          }
          bubble.closed = true;
        }
        delete openIds[ev.role];
      }
      continue;
    }
    if (isStream(ev) && ev.kind === "token" && ev.role && ev.text) {
      const role = ev.role;
      let id = openIds[role];
      if (!id) {
        id = `${role}-${ev.seq ?? lanes[role].bubbles.length}`;
        lanes[role].bubbles.push({
          id,
          role,
          text: "",
          closed: false,
        });
        openIds[role] = id;
      }
      const bubble = lanes[role].bubbles.find((b) => b.id === id);
      if (bubble) bubble.text += ev.text;
    }
  }

  return ROLE_ORDER.map((r) => lanes[r]);
}

interface DebateStreamProps {
  events: WireEvent[];
  className?: string;
}

export function DebateStream({ events, className }: DebateStreamProps): JSX.Element {
  const lanes = useMemo(() => buildLanes(events), [events]);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    // Scroll the most recent bubble into view as new tokens land.
    el.scrollTop = el.scrollHeight;
  }, [events.length]);

  return (
    <div
      ref={containerRef}
      className={cn(
        "grid max-h-[70vh] grid-cols-1 gap-3 overflow-y-auto pr-1 lg:grid-cols-2",
        className,
      )}
    >
      {lanes.map((lane) => (
        <Card key={lane.role}>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-base">{lane.role}</CardTitle>
            <Badge variant="outline" className={cn("font-mono text-[10px]", ROLE_TONE[lane.role])}>
              {lane.bubbles.length} turn{lane.bubbles.length === 1 ? "" : "s"}
            </Badge>
          </CardHeader>
          <CardContent className="space-y-2">
            {lane.bubbles.length === 0 ? (
              <p className="text-xs italic text-muted-foreground">Waiting…</p>
            ) : (
              lane.bubbles.map((b) => (
                <div
                  key={b.id}
                  className={cn(
                    "rounded-md border p-3 font-mono text-xs leading-relaxed",
                    ROLE_TONE[b.role],
                    !b.closed && "animate-pulse",
                  )}
                >
                  <pre className="whitespace-pre-wrap break-words">{b.text || "…"}</pre>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
