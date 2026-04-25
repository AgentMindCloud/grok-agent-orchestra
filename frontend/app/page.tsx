import type { Metadata } from "next";
import { Suspense } from "react";

import { RecentRuns } from "@/components/recent-runs";
import { RunTrigger } from "@/components/run-trigger";
import { TemplatePicker } from "@/components/template-picker";

export const metadata: Metadata = {
  title: "Dashboard",
  description:
    "Pick a template, hit Run, and watch the Grok / Harper / Benjamin / Lucas debate stream live.",
};

export default function HomePage(): JSX.Element {
  return (
    <div className="grid gap-8 lg:grid-cols-[3fr_2fr]">
      <section className="space-y-6">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            Pick a template, hit Run.
          </h1>
          <p className="mt-2 max-w-prose text-muted-foreground">
            Four named roles — Grok, Harper, Benjamin, Lucas — argue on
            screen and ship a citation-rich report. Lucas&rsquo;s strict-JSON
            veto is the framework&rsquo;s safety gate; nothing leaves the box
            without it.
          </p>
        </div>

        <Suspense fallback={<div className="h-72 animate-pulse rounded-md bg-muted" />}>
          <TemplatePicker />
        </Suspense>

        <RunTrigger />
      </section>

      <aside className="space-y-6">
        <Suspense fallback={<div className="h-48 animate-pulse rounded-md bg-muted" />}>
          <RecentRuns />
        </Suspense>
      </aside>
    </div>
  );
}
