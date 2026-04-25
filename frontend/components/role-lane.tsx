"use client";

import { motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";

import { RoleAvatar } from "@/components/role-avatar";
import { RoleMessage } from "@/components/role-message";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { roleMeta } from "@/lib/role-meta";
import type { RoleLaneModel } from "@/lib/use-stream-model";
import { cn } from "@/lib/utils";

interface RoleLaneProps {
  lane: RoleLaneModel;
  className?: string;
  /**
   * Cap the number of rendered messages. Older messages collapse into
   * a "+N earlier" header so the DOM stays bounded on long runs.
   * Default: 80 messages (≈ 200 KB of HTML even with verbose tokens).
   */
  windowSize?: number;
}

export function RoleLane({
  lane,
  className,
  windowSize = 80,
}: RoleLaneProps): JSX.Element {
  const meta = roleMeta(lane.role);
  const isActive = lane.openMessageId !== null;
  const visible = useMemo(
    () =>
      lane.messages.length > windowSize
        ? lane.messages.slice(-windowSize)
        : lane.messages,
    [lane.messages, windowSize],
  );
  const truncated = lane.messages.length - visible.length;

  // Auto-scroll only when the user is already near the bottom — never
  // wrench the scroll position out from under someone reading older
  // messages.
  const scrollRef = useRef<HTMLDivElement>(null);
  const [stickToBottom, setStickToBottom] = useState(true);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || !stickToBottom) return;
    el.scrollTop = el.scrollHeight;
  }, [lane.messages.length, stickToBottom]);

  function onScroll(e: React.UIEvent<HTMLDivElement>): void {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    const distance = scrollHeight - (scrollTop + clientHeight);
    setStickToBottom(distance < 80);
  }

  return (
    <motion.section
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, ease: "easeOut" }}
      className={cn(
        "flex h-full min-h-[40vh] flex-col rounded-lg border bg-card/30 shadow-sm",
        meta.laneClass,
        className,
      )}
      aria-label={`${lane.role} lane`}
    >
      <header className="flex items-center justify-between gap-3 border-b border-border/60 p-3">
        <div className="flex items-center gap-2.5">
          <RoleAvatar role={lane.role} active={isActive} />
          <div>
            <p className={cn("text-sm font-semibold", meta.textClass)}>
              {meta.name}
            </p>
            <p className="text-[11px] text-muted-foreground">{meta.oneLine}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {lane.totalCitations > 0 ? (
            <Badge variant="outline" className="text-[10px]">
              {lane.totalCitations} cite{lane.totalCitations === 1 ? "" : "s"}
            </Badge>
          ) : null}
          {isActive ? (
            <Badge className={cn("text-[10px] uppercase", meta.textClass)} variant="outline">
              speaking
            </Badge>
          ) : null}
        </div>
      </header>

      <ScrollArea className="flex-1">
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className="flex h-full max-h-[60vh] flex-col gap-2 overflow-y-auto p-3"
        >
          {truncated > 0 ? (
            <p className="rounded-md border border-dashed border-border/60 px-2 py-1 text-center text-[11px] text-muted-foreground">
              + {truncated} earlier message{truncated === 1 ? "" : "s"}
            </p>
          ) : null}
          {visible.length === 0 ? (
            <p className="my-auto text-center text-xs italic text-muted-foreground">
              Waiting…
            </p>
          ) : (
            visible.map((m) => <RoleMessage key={m.id} message={m} />)
          )}
        </div>
      </ScrollArea>
    </motion.section>
  );
}
