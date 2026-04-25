import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Agent Orchestra — multi-agent research with visible debate.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage(): ImageResponse {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 64,
          background:
            "linear-gradient(135deg, #0d0d0d 0%, #1a0d05 60%, #ff6b35 140%)",
          color: "#fff7ec",
          fontFamily: "Inter, system-ui, sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              width: 18,
              height: 18,
              borderRadius: 999,
              background: "#ff6b35",
              boxShadow: "0 0 24px rgba(255,107,53,0.6)",
            }}
          />
          <span style={{ fontSize: 28, opacity: 0.85, letterSpacing: 0.5 }}>
            agentmindcloud / grok-agent-orchestra
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <span style={{ fontSize: 88, fontWeight: 700, lineHeight: 1.05 }}>
            Multi-agent research,
            <br />
            visible debate,
            <br />
            enforceable veto.
          </span>
          <span style={{ fontSize: 28, opacity: 0.8, maxWidth: 880 }}>
            Grok · Harper · Benjamin · Lucas — argue on screen, ship a
            citation-rich report.
          </span>
        </div>
        <div style={{ display: "flex", gap: 24, fontSize: 24, opacity: 0.85 }}>
          <span>● Native multi-agent</span>
          <span>● Lucas safety veto</span>
          <span>● BYOK · LiteLLM · MCP</span>
        </div>
      </div>
    ),
    { ...size },
  );
}
