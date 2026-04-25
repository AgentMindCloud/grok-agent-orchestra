/**
 * Lucas judge bench. Same shape as the Next.js version but
 * minimal — confidence pill + verdict log. No animation; the inner-
 * loop user wants signal density, not polish.
 */

export interface LucasState {
  status: "idle" | "observing" | "passed" | "vetoed";
  confidence: number | null;
  verdicts: Array<{
    kind: "passed" | "vetoed";
    confidence?: number;
    reason?: string;
    blockedContent?: string;
  }>;
}

const STATUS_COLOR: Record<LucasState["status"], string> = {
  idle: "var(--vscode-descriptionForeground)",
  observing: "var(--vscode-charts-yellow, #d3a04a)",
  passed: "var(--vscode-charts-green, #5fc37a)",
  vetoed: "var(--vscode-errorForeground, #e85a5a)",
};

const STATUS_LABEL: Record<LucasState["status"], string> = {
  idle: "stand-by",
  observing: "observing",
  passed: "passed",
  vetoed: "vetoed",
};

export function LucasPanel({ state }: { state: LucasState }): JSX.Element {
  const color = STATUS_COLOR[state.status];
  const conf = state.confidence === null ? null : Math.round(state.confidence * 100);
  return (
    <aside
      aria-label="Lucas judge bench"
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        border: "1px solid var(--vscode-panel-border)",
        borderRadius: 6,
        background: "var(--vscode-sideBar-background)",
      }}
    >
      <header style={{ padding: "8px 10px", borderBottom: "1px solid var(--vscode-panel-border)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong>Lucas</strong>
          <span style={{ color, fontSize: "0.85em", textTransform: "uppercase", fontWeight: 600 }}>
            {STATUS_LABEL[state.status]}
          </span>
        </div>
        <div style={{ marginTop: 4, display: "flex", justifyContent: "space-between", fontSize: "0.8em", color: "var(--vscode-descriptionForeground)" }}>
          <span>confidence</span>
          <span>{conf === null ? "—" : `${conf}%`}</span>
        </div>
        <div style={{ marginTop: 4, height: 4, borderRadius: 2, background: "var(--vscode-progressBar-background)" }}>
          <div
            style={{
              height: "100%",
              width: `${conf ?? 0}%`,
              background: state.status === "vetoed" ? "var(--vscode-errorForeground)" : color,
              transition: "width 250ms ease-out",
              borderRadius: 2,
            }}
          />
        </div>
      </header>
      <ol style={{ flex: 1, margin: 0, padding: "8px 10px", overflowY: "auto", listStyle: "none" }}>
        {state.verdicts.length === 0 ? (
          <li style={{ fontStyle: "italic", color: "var(--vscode-descriptionForeground)" }}>
            Lucas hasn&rsquo;t said a word yet.
          </li>
        ) : (
          state.verdicts.slice().reverse().map((v, i) => (
            <li
              key={i}
              style={{
                padding: 6,
                marginBottom: 6,
                borderRadius: 4,
                border: "1px solid",
                borderColor:
                  v.kind === "vetoed"
                    ? "var(--vscode-errorForeground)"
                    : "var(--vscode-charts-green, #5fc37a)80",
                background:
                  v.kind === "vetoed"
                    ? "var(--vscode-inputValidation-errorBackground)"
                    : "transparent",
                fontSize: "0.85em",
              }}
            >
              <strong style={{ color: v.kind === "vetoed" ? "var(--vscode-errorForeground)" : "var(--vscode-charts-green, #5fc37a)" }}>
                {v.kind === "vetoed" ? "VETOED" : "PASSED"}
              </strong>
              {typeof v.confidence === "number" ? (
                <span style={{ marginLeft: 6, color: "var(--vscode-descriptionForeground)" }}>
                  conf {v.confidence.toFixed(2)}
                </span>
              ) : null}
              {v.reason ? <p style={{ margin: "4px 0 0" }}>{v.reason}</p> : null}
              {v.blockedContent ? (
                <details style={{ marginTop: 4, color: "var(--vscode-descriptionForeground)" }}>
                  <summary style={{ cursor: "pointer", fontSize: "0.85em" }}>show blocked</summary>
                  <pre style={{ margin: "4px 0 0", padding: 4, fontSize: "0.85em", whiteSpace: "pre-wrap" }}>
                    {v.blockedContent}
                  </pre>
                </details>
              ) : null}
            </li>
          ))
        )}
      </ol>
    </aside>
  );
}
