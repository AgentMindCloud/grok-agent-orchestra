import { RunDetailView } from "@/components/run-detail-view";

interface RunPageProps {
  params: { runId: string };
}

export default function RunPage({ params }: RunPageProps): JSX.Element {
  return <RunDetailView runId={params.runId} />;
}
