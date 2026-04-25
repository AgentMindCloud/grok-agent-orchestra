/**
 * Single source of truth for per-role metadata. Keeps lane colours,
 * avatar glyphs, and one-line descriptions in one place so the role
 * lane, the Lucas panel, and the run header all agree.
 *
 * Visual treatment is deliberately tactile (judge bench / writers'
 * room / courtroom) without leaning on glass-blur tricks. Tailwind
 * tokens are pulled from the `--role-*` CSS variables defined in
 * `app/globals.css` so dark/light mode stays in sync.
 */

import type { RoleName } from "@/lib/events";

export interface RoleMeta {
  name: RoleName;
  glyph: string;                    // single-character avatar glyph
  oneLine: string;                  // tooltip / aria-label
  description: string;              // longer hover description
  laneClass: string;                // lane shell (border + bg accent)
  ringClass: string;                // ring used by the avatar bubble
  textClass: string;                // role-coloured text
  borderClass: string;              // role-coloured border for cards
  bgClass: string;                  // tinted background for messages
  caretClass: string;               // streaming caret colour
}

const ROLE_META_INTERNAL: Record<RoleName, RoleMeta> = {
  Grok: {
    name: "Grok",
    glyph: "G",
    oneLine: "Executive coordinator",
    description:
      "Sets the agenda each round, weighs Harper's evidence against Benjamin's logic, and synthesises the final post.",
    laneClass: "border-role-grok/30 bg-role-grok/[0.04]",
    ringClass: "ring-role-grok/40",
    textClass: "text-role-grok",
    borderClass: "border-role-grok/40",
    bgClass: "bg-role-grok/[0.06]",
    caretClass: "after:bg-role-grok",
  },
  Harper: {
    name: "Harper",
    glyph: "H",
    oneLine: "Researcher",
    description:
      "Searches the web, reads local docs, calls MCP tools. Cites every claim or admits the gap.",
    laneClass: "border-role-harper/30 bg-role-harper/[0.04]",
    ringClass: "ring-role-harper/40",
    textClass: "text-role-harper",
    borderClass: "border-role-harper/40",
    bgClass: "bg-role-harper/[0.06]",
    caretClass: "after:bg-role-harper",
  },
  Benjamin: {
    name: "Benjamin",
    glyph: "B",
    oneLine: "Logician",
    description:
      "Stress-tests the math, runs code for numerical checks, hunts contradictions in Harper's findings.",
    laneClass: "border-role-benjamin/30 bg-role-benjamin/[0.04]",
    ringClass: "ring-role-benjamin/40",
    textClass: "text-role-benjamin",
    borderClass: "border-role-benjamin/40",
    bgClass: "bg-role-benjamin/[0.06]",
    caretClass: "after:bg-role-benjamin",
  },
  Lucas: {
    name: "Lucas",
    glyph: "L",
    oneLine: "Contrarian + safety judge",
    description:
      "Reads the synthesis like an adversarial reviewer. Strict-JSON veto, fail-closed defaults — nothing ships without him.",
    laneClass: "border-role-lucas/30 bg-role-lucas/[0.04]",
    ringClass: "ring-role-lucas/50",
    textClass: "text-role-lucas",
    borderClass: "border-role-lucas/40",
    bgClass: "bg-role-lucas/[0.06]",
    caretClass: "after:bg-role-lucas",
  },
};

export function roleMeta(name: RoleName): RoleMeta {
  return ROLE_META_INTERNAL[name];
}

// Lanes shown in the courtroom layout. Lucas is rendered separately
// in the judge-bench panel — not as a lane.
export const LANE_ROLES: RoleName[] = ["Harper", "Benjamin", "Grok"];

// Every role we can attribute, including Lucas (used by message tinting
// when Lucas voices speak through the stream rather than the panel).
export const ALL_ROLES: RoleName[] = ["Harper", "Benjamin", "Grok", "Lucas"];
