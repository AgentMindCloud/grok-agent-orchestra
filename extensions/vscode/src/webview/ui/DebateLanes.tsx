/**
 * Three role lanes (Harper / Benjamin / Grok). Lucas is rendered
 * separately as the judge bench. Pure inline styles so the bundle
 * needs no external CSS file.
 */

interface Bubble {
  id: string;
  text: string;
  closed: boolean;
  status: "ok" | "vetoed";
}

export type LaneState = {
  Harper: Bubble[];
  Benjamin: Bubble[];
  Grok: Bubble[];
  Lucas: Bubble[];
};

const ROLE_COLOR: Record<keyof LaneState, string> = {
  Harper: "var(--vscode-charts-blue, #5fb3d4)",
  Benjamin: "var(--vscode-charts-yellow, #d3a04a)",
  Grok: "var(--vscode-charts-orange, #ff7a45)",
  Lucas: "var(--vscode-charts-red, #e85a5a)",
};

const LANE_ROLES: Array<keyof LaneState> = ["Harper", "Benjamin", "Grok"];

export function DebateLanes({ lanes }: { lanes: LaneState }): JSX.Element {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8, minHeight: 0 }}>
      {LANE_ROLES.map((role) => (
        <Lane key={role} role={role} bubbles={lanes[role]} />
      ))}
    </div>
  );
}

function Lane({ role, bubbles }: { role: keyof LaneState; bubbles: Bubble[] }): JSX.Element {
  const color = ROLE_COLOR[role];
  return (
    <section
      aria-label={`${role} lane`}
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        border: `1px solid ${color}40`,
        borderRadius: 6,
        background: `${color}0a`,
      }}
    >
      <header
        style={{
          padding: "6px 10px",
          borderBottom: `1px solid ${color}30`,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "0.85em",
          fontWeight: 600,
          color,
        }}
      >
        <span>{role}</span>
        <span style={{ opacity: 0.6 }}>{bubbles.length} turn{bubbles.length === 1 ? "" : "s"}</span>
      </header>
      <div style={{ flex: 1, overflowY: "auto", padding: 8, display: "flex", flexDirection: "column", gap: 6 }}>
        {bubbles.length === 0 ? (
          <span style={{ fontStyle: "italic", color: "var(--vscode-descriptionForeground)", textAlign: "center", marginTop: 24 }}>
            Waiting…
          </span>
        ) : (
          bubbles.map((b) => (
            <div
              key={b.id}
              style={{
                padding: "6px 8px",
                borderRadius: 4,
                background: b.status === "vetoed" ? "var(--vscode-inputValidation-errorBackground)" : "var(--vscode-editor-inactiveSelectionBackground)",
                border: b.status === "vetoed" ? "1px solid var(--vscode-inputValidation-errorBorder)" : "1px solid transparent",
                fontFamily: "var(--vscode-editor-font-family, monospace)",
                fontSize: "0.85em",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                opacity: b.closed ? 1 : 0.85,
              }}
            >
              {b.text || "…"}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
