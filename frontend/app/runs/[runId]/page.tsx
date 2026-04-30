import { RunDetailView } from "@/components/run-detail-view";

interface RunPageProps {
  params: { runId: string };
}

// Static export (`NEXT_BUILD_TARGET=export pnpm build`) requires every
// dynamic segment to declare `generateStaticParams()` — and Next 14
// rejects an empty array, so we ship a single placeholder route. The
// FastAPI backend rewrites every /runs/<actualId> request to the same
// shell HTML, so the placeholder is never user-visible. Node mode
// keeps `dynamicParams` defaulting to `true` and renders new IDs on
// demand without using this list at all.
export function generateStaticParams(): { runId: string }[] {
  return [{ runId: "_shell" }];
}

export function generateMetadata({ params }: RunPageProps): {
  title: string;
  description: string;
} {
  return {
    title: `Run ${params.runId.slice(0, 8)}`,
    description:
      "Live debate stream — Grok / Harper / Benjamin under Lucas's safety judgment.",
  };
}

export default function RunPage({ params }: RunPageProps): JSX.Element {
  // `RunDetailView` carries the `"use client"` pragma itself, so importing
  // it from a Server Component is fine — Next routes the boundary
  // automatically and the client runtime hydrates the WebSocket.
  return <RunDetailView runId={params.runId} />;
}
