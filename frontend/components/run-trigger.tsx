"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ApiError, api } from "@/lib/api-client";
import { useSelectedTemplate } from "@/lib/selection-store";

export function RunTrigger(): JSX.Element {
  const router = useRouter();
  const selected = useSelectedTemplate();
  const [simulated, setSimulated] = useState(true);
  const [yamlText, setYamlText] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!selected) {
      setYamlText("");
      return;
    }
    setErr(null);
    api
      .getTemplate(selected)
      .then((tpl) => setYamlText(tpl.yaml))
      .catch((e) =>
        setErr(e instanceof ApiError ? e.message : "Failed to load template"),
      );
  }, [selected]);

  async function onRun(): Promise<void> {
    setBusy(true);
    setErr(null);
    try {
      const { run_id } = await api.startRun({
        yaml: yamlText,
        inputs: {},
        simulated,
        template_name: selected ?? undefined,
      });
      router.push(`/runs/${run_id}`);
    } catch (e) {
      setErr(
        e instanceof ApiError
          ? `${e.message}${e.detail ? `: ${e.detail}` : ""}`
          : String(e),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle>Run</CardTitle>
          <CardDescription>
            {selected
              ? "Selected template ready to run."
              : "Pick a template to enable Run."}
          </CardDescription>
        </div>
        {selected ? <Badge variant="secondary">{selected}</Badge> : null}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-3">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-input accent-primary"
              checked={simulated}
              onChange={(e) => setSimulated(e.target.checked)}
            />
            Simulated (no API key required)
          </label>
        </div>
        <div className="flex items-center gap-3">
          <Button onClick={onRun} disabled={busy || !yamlText.trim()}>
            {busy ? "Starting…" : "▶ Run"}
          </Button>
          {err ? (
            <span className="text-sm text-destructive">{err}</span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
