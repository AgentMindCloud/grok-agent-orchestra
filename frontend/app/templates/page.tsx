import type { Metadata } from "next";

import { TemplateBrowser } from "@/components/template-browser";

export const metadata: Metadata = {
  title: "Templates",
  description:
    "Browse the certified Agent Orchestra YAML templates — research, business, debate, code-review patterns.",
};

// Templates rarely change between runs; let Next cache the shell.
export const revalidate = 300;

export default function TemplatesPage(): JSX.Element {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Templates</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">
          Eighteen certified templates. Each one is a complete YAML spec
          that runs unmodified — pick one, click <em>Show YAML</em>, then
          run it from the dashboard.
        </p>
      </div>
      <TemplateBrowser />
    </div>
  );
}
