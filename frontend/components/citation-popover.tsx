"use client";

import { ExternalLink, FileText, Globe2, Plug } from "lucide-react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { citationHref, type Citation } from "@/lib/citations";
import { cn } from "@/lib/utils";

const ICON_FOR = {
  web: Globe2,
  file: FileText,
  doc: FileText,
  mcp: Plug,
} as const;

interface CitationPopoverProps {
  citation: Citation;
}

export function CitationPopover({ citation }: CitationPopoverProps): JSX.Element {
  const Icon = ICON_FOR[citation.scheme];
  const href = citationHref(citation);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Source: ${citation.label}`}
          className={cn(
            "inline-flex items-baseline gap-1 rounded border border-border/60 bg-muted/40 px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground align-baseline",
            "transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-foreground",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          )}
        >
          <Icon className="h-3 w-3" aria-hidden />
          <span className="truncate max-w-[12rem]">{citation.label}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent>
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 text-muted-foreground" aria-hidden />
            <span className="text-xs uppercase tracking-wider text-muted-foreground">
              {citation.scheme}
            </span>
          </div>
          <p className="break-all text-sm font-medium">{citation.target}</p>
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-primary underline-offset-4 hover:underline"
            >
              Open <ExternalLink className="h-3 w-3" aria-hidden />
            </a>
          ) : (
            <p className="text-xs text-muted-foreground">
              Local citation — open the run&rsquo;s workspace folder to inspect.
            </p>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
