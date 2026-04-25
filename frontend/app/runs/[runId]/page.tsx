import dynamic from "next/dynamic";

import { SkeletonLanes } from "@/components/skeleton-lanes";

// The run detail view pulls in framer-motion + every Radix primitive
// + the WS hook. Dynamic-import keeps the dashboard root chunk light;
// SSR off because the page is dependent on a live WebSocket (no
// useful server output, just hydration cost).
const RunDetailView = dynamic(
  () => import("@/components/run-detail-view").then((m) => m.RunDetailView),
  { ssr: false, loading: () => <SkeletonLanes /> },
);

interface RunPageProps {
  params: { runId: string };
}

export const dynamicParams = true;

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
  return <RunDetailView runId={params.runId} />;
}
