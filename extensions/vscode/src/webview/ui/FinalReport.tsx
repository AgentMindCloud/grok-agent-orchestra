/**
 * Final-report card — collapses while the run is in flight; reveals
 * the truncated synthesis + a download / open link once the result
 * lands. Keeps the inline preview at 8 KB to match the SKILL's
 * truncation contract.
 */

import type { RunResult } from "./api";

const PREVIEW_BYTES = 8 * 1024;

export function FinalReport({ result }: { result: RunResult | null }): JSX.Element | null {
  if (!result) return null;
  const preview = truncate(result.finalContent, PREVIEW_BYTES);

  return (
    <section
      aria-label="Final report"
      style={{
        border: "1px solid var(--vscode-panel-border)",
        borderRadius: 6,
        padding: 12,
        background: "var(--vscode-sideBar-background)",
        maxHeight: "32vh",
        overflowY: "auto",
      }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
        <strong>Final synthesis</strong>
        <span style={{ fontSize: "0.8em", color: "var(--vscode-descriptionForeground)" }}>
          run {result.runId ?? "—"} · {result.durationSeconds.toFixed(1)}s · exit {result.exitCode}
        </span>
      </header>
      {result.errorMessage ? (
        <pre
          style={{
            background: "var(--vscode-inputValidation-errorBackground)",
            color: "var(--vscode-errorForeground)",
            padding: 8,
            borderRadius: 4,
            whiteSpace: "pre-wrap",
            fontSize: "0.85em",
          }}
        >
          {result.errorMessage}
        </pre>
      ) : null}
      <pre
        style={{
          margin: 0,
          fontSize: "0.85em",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
          fontFamily: "var(--vscode-editor-font-family, monospace)",
        }}
      >
        {preview || "(no content)"}
      </pre>
    </section>
  );
}

function truncate(text: string, maxBytes: number): string {
  const enc = new TextEncoder();
  const bytes = enc.encode(text);
  if (bytes.length <= maxBytes) return text;
  const dec = new TextDecoder("utf-8");
  const headLen = Math.floor(maxBytes * 0.75);
  const tailLen = maxBytes - headLen - 64;
  const head = dec.decode(bytes.slice(0, headLen)).replace(/�+$/, "");
  const tail = dec.decode(bytes.slice(bytes.length - tailLen)).replace(/^�+/, "");
  return `${head}\n\n…(truncated; ${bytes.length} bytes total)…\n\n${tail}`;
}
