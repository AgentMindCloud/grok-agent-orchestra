import type { Metadata } from "next";

import { SettingsForm } from "@/components/settings-form";

export const metadata: Metadata = {
  title: "Settings",
  description: "Configure backend URL, default workflow, model aliases, tracing, and theme.",
};

export default function SettingsPage(): JSX.Element {
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-2 text-muted-foreground">
          Per-browser overrides for the API base URL. Useful when the
          backend lives on a non-default port or when you&rsquo;re hitting
          a remote dev box.
        </p>
      </div>
      <SettingsForm />
    </div>
  );
}
