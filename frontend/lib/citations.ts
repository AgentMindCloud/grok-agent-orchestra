/**
 * Tiny citation extractor. Pulls bracketed source markers out of
 * agent text so the renderer can replace them with hover popovers
 * without needing a server-side parse.
 *
 * Supported forms (the ones our agents actually emit):
 *
 *   [web:example.com]                 — bare host
 *   [web:https://example.com/page]    — full URL
 *   [file:./report.pdf#page=4]        — local file with anchor
 *   [doc:my-internal-spec]            — opaque doc id
 *
 * The parser is intentionally tolerant — anything inside brackets that
 * starts with `<scheme>:` is a Citation. Bracketed strings without the
 * `:` separator are passed through as plain text.
 */

import type { RoleName } from "@/lib/events";

export type CitationScheme = "web" | "file" | "doc" | "mcp";

export interface Citation {
  scheme: CitationScheme;
  /** Raw target after the scheme — may be a URL, host, or opaque id. */
  target: string;
  /** Display label — host for URLs, basename for files. */
  label: string;
  /** Original full match including brackets. */
  raw: string;
}

export type SegmentKind = "text" | "citation";

export type Segment =
  | { kind: "text"; text: string }
  | { kind: "citation"; citation: Citation };

const CITE_RE = /\[(web|file|doc|mcp):([^\]]+)\]/g;

function labelFor(scheme: CitationScheme, target: string): string {
  const t = target.trim();
  if (scheme === "web") {
    try {
      const url = t.startsWith("http") ? new URL(t) : new URL(`https://${t}`);
      return url.host;
    } catch {
      return t;
    }
  }
  if (scheme === "file") {
    const noQuery = t.split(/[?#]/)[0];
    return noQuery.split("/").pop() || t;
  }
  return t;
}

export function extractCitations(text: string): Citation[] {
  const out: Citation[] = [];
  for (const m of text.matchAll(CITE_RE)) {
    const scheme = m[1] as CitationScheme;
    const target = m[2];
    out.push({ scheme, target, label: labelFor(scheme, target), raw: m[0] });
  }
  return out;
}

/**
 * Split a string into alternating text and citation segments — the
 * shape `<RoleMessage>` consumes when it renders citations as
 * hoverable popovers instead of plain text.
 */
export function segmentsOf(text: string): Segment[] {
  if (!text) return [];
  const segments: Segment[] = [];
  let lastEnd = 0;
  for (const m of text.matchAll(CITE_RE)) {
    const start = m.index ?? 0;
    if (start > lastEnd) {
      segments.push({ kind: "text", text: text.slice(lastEnd, start) });
    }
    const scheme = m[1] as CitationScheme;
    const target = m[2];
    segments.push({
      kind: "citation",
      citation: { scheme, target, label: labelFor(scheme, target), raw: m[0] },
    });
    lastEnd = start + m[0].length;
  }
  if (lastEnd < text.length) {
    segments.push({ kind: "text", text: text.slice(lastEnd) });
  }
  return segments;
}

/**
 * Resolve a citation's outbound href. Web → URL. Files / docs → null
 * (the popover renders the target inline; the runner stores artefacts
 * in the workspace, not on a public URL).
 */
export function citationHref(citation: Citation): string | null {
  if (citation.scheme === "web") {
    const t = citation.target.trim();
    return t.startsWith("http") ? t : `https://${t}`;
  }
  return null;
}

/**
 * Compute the cumulative citation count per role. Used by the
 * lane header to surface "12 citations" without an O(n) scan
 * inside the render path.
 */
export function citationCountByRole(
  perRole: Record<RoleName, string[]>,
): Record<RoleName, number> {
  const out = {} as Record<RoleName, number>;
  for (const role of Object.keys(perRole) as RoleName[]) {
    let total = 0;
    for (const t of perRole[role]) total += extractCitations(t).length;
    out[role] = total;
  }
  return out;
}
