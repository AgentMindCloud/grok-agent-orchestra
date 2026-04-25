"use client";

import { motion } from "framer-motion";
import { Check, Copy, Download, FileText } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ApiClient } from "@/lib/api-client";

interface FinalOutputPanelProps {
  runId: string;
  text: string | null;
  failureReason: string | null;
}

export function FinalOutputPanel({
  runId,
  text,
  failureReason,
}: FinalOutputPanelProps): JSX.Element {
  const [copied, setCopied] = useState(false);
  const apiClient = new ApiClient();

  if (failureReason) {
    return (
      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="text-destructive">Run failed</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm">{failureReason}</p>
        </CardContent>
      </Card>
    );
  }

  if (!text) return <div aria-hidden />;

  async function onCopy(): Promise<void> {
    if (!text) return;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <motion.section
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.24, ease: "easeOut" }}
    >
      <Card className="border-emerald-500/30 bg-gradient-to-br from-background via-background to-emerald-500/5">
        <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0">
          <CardTitle className="inline-flex items-center gap-2 text-base">
            <FileText className="h-4 w-4 text-emerald-500" aria-hidden />
            Final synthesis
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={onCopy}>
              {copied ? (
                <Check className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              ) : (
                <Copy className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              )}
              {copied ? "Copied" : "Copy"}
            </Button>
            <Button asChild variant="outline" size="sm">
              <a href={apiClient.reportUrl(runId, "md")} target="_blank" rel="noreferrer">
                <Download className="mr-1.5 h-3.5 w-3.5" aria-hidden /> .md
              </a>
            </Button>
            <Button asChild variant="outline" size="sm">
              <a href={apiClient.reportUrl(runId, "pdf")} target="_blank" rel="noreferrer">
                <Download className="mr-1.5 h-3.5 w-3.5" aria-hidden /> .pdf
              </a>
            </Button>
            <Button asChild variant="outline" size="sm">
              <a href={apiClient.reportUrl(runId, "docx")} target="_blank" rel="noreferrer">
                <Download className="mr-1.5 h-3.5 w-3.5" aria-hidden /> .docx
              </a>
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <pre className="max-h-[40vh] overflow-y-auto whitespace-pre-wrap break-words rounded-md border bg-muted/30 p-4 font-mono text-sm leading-relaxed">
            {text}
          </pre>
        </CardContent>
      </Card>
    </motion.section>
  );
}
