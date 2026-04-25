"use client";

import { motion } from "framer-motion";
import { ShieldAlert } from "lucide-react";
import { Fragment, memo } from "react";

import { CitationPopover } from "@/components/citation-popover";
import { RoleToolCall } from "@/components/role-tool-call";
import { Badge } from "@/components/ui/badge";
import { segmentsOf } from "@/lib/citations";
import { roleMeta } from "@/lib/role-meta";
import type { RoleMessage as RoleMessageModel } from "@/lib/use-stream-model";
import { cn } from "@/lib/utils";

interface RoleMessageProps {
  message: RoleMessageModel;
}

function MessageInner({ message }: RoleMessageProps): JSX.Element {
  const meta = roleMeta(message.role);
  const segments = segmentsOf(message.text);
  const isStreaming = message.status === "streaming";
  const isVetoed = message.status === "vetoed";

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className={cn(
        "rounded-md border bg-card/60 p-3 text-sm leading-relaxed shadow-sm",
        meta.borderClass,
        isVetoed && "border-destructive/60 bg-destructive/5 ring-2 ring-destructive/30",
      )}
      data-status={message.status}
      data-role={message.role}
    >
      {isVetoed ? (
        <div className="mb-2 inline-flex items-center gap-1.5 rounded-md border border-destructive/40 bg-destructive/10 px-2 py-0.5 text-[11px] font-medium text-destructive">
          <ShieldAlert className="h-3 w-3" aria-hidden /> vetoed by Lucas
        </div>
      ) : null}

      <div
        className={cn(
          "font-mono text-xs leading-relaxed text-foreground/90",
          // Streaming caret — pure CSS, paused by reduced-motion media query.
          isStreaming &&
            cn(
              "after:ml-0.5 after:inline-block after:h-3 after:w-[2px] after:translate-y-[1px] after:animate-caret-blink motion-reduce:after:animate-none",
              meta.caretClass,
            ),
        )}
      >
        {segments.length === 0 && isStreaming ? (
          <span className="italic text-muted-foreground">…</span>
        ) : (
          segments.map((seg, i) =>
            seg.kind === "text" ? (
              <Fragment key={i}>{seg.text}</Fragment>
            ) : (
              <span key={i} className="mx-0.5">
                <CitationPopover citation={seg.citation} />
              </span>
            ),
          )
        )}
      </div>

      {message.toolCalls.length > 0 ? (
        <div className="mt-2.5 grid gap-1.5">
          {message.toolCalls.map((tc) => (
            <RoleToolCall key={tc.id} call={tc} />
          ))}
        </div>
      ) : null}

      {message.citationCount > 0 || isStreaming ? (
        <div className="mt-2 flex items-center justify-between text-[10px] text-muted-foreground">
          <span>
            {message.citationCount > 0
              ? `${message.citationCount} citation${message.citationCount === 1 ? "" : "s"}`
              : null}
          </span>
          {isStreaming ? (
            <Badge variant="outline" className="text-[10px] uppercase">
              streaming
            </Badge>
          ) : null}
        </div>
      ) : null}
    </motion.article>
  );
}

// Memoise — the lane re-renders on every batched frame, but a closed
// message hasn't changed once `status: "done"`.
export const RoleMessage = memo(
  MessageInner,
  (prev, next) =>
    prev.message.id === next.message.id &&
    prev.message.text === next.message.text &&
    prev.message.status === next.message.status &&
    prev.message.toolCalls.length === next.message.toolCalls.length,
);
