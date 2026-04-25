"use client";

import { Plus, Trash2 } from "lucide-react";
import { useTheme } from "next-themes";
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
import { Separator } from "@/components/ui/separator";
import {
  DEFAULT_SETTINGS,
  KNOWN_PROVIDERS,
  loadSettings,
  saveSettings,
  type ModelAlias,
  type Settings,
} from "@/lib/settings";

export function SettingsForm(): JSX.Element {
  const { theme, setTheme } = useTheme();
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setSettings(loadSettings());
  }, []);

  function update<K extends keyof Settings>(key: K, value: Settings[K]): void {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  function updateAlias(idx: number, patch: Partial<ModelAlias>): void {
    setSettings((prev) => {
      const next = [...prev.modelAliases];
      next[idx] = { ...next[idx], ...patch };
      return { ...prev, modelAliases: next };
    });
    setSaved(false);
  }

  function addAlias(): void {
    setSettings((prev) => ({
      ...prev,
      modelAliases: [
        ...prev.modelAliases,
        { alias: "", provider: "xai", model: "" },
      ],
    }));
  }

  function removeAlias(idx: number): void {
    setSettings((prev) => ({
      ...prev,
      modelAliases: prev.modelAliases.filter((_, i) => i !== idx),
    }));
    setSaved(false);
  }

  function onSubmit(e: React.FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    saveSettings(settings);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  }

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      {/* ---------- Backend ---------- */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Backend</CardTitle>
          <CardDescription>
            Per-browser overrides. Stored in <code className="font-mono">localStorage</code>;
            never sent to any third party.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Field
            label="API base URL"
            hint="Leave blank to use NEXT_PUBLIC_API_URL."
          >
            <input
              type="url"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              placeholder="http://localhost:8000"
              value={settings.apiBaseUrl}
              onChange={(e) => update("apiBaseUrl", e.target.value)}
            />
          </Field>
        </CardContent>
      </Card>

      {/* ---------- Defaults ---------- */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Defaults</CardTitle>
          <CardDescription>
            Pre-selects every new run on the dashboard.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2">
          <Field label="Default workflow">
            <select
              value={settings.defaultWorkflow}
              onChange={(e) =>
                update("defaultWorkflow", e.target.value as Settings["defaultWorkflow"])
              }
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="auto">auto (resolve from YAML)</option>
              <option value="native">native (Grok multi-agent)</option>
              <option value="simulated">simulated (multi-call)</option>
              <option value="deep_research">deep_research</option>
            </select>
          </Field>
          <Field label="Default model" hint="Model id, e.g. grok-4-0709">
            <input
              type="text"
              value={settings.defaultModel}
              onChange={(e) => update("defaultModel", e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
            />
          </Field>
        </CardContent>
      </Card>

      {/* ---------- Model aliases ---------- */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Model aliases</CardTitle>
          <CardDescription>
            UI for the YAML <code className="font-mono">orchestra.llm.aliases</code> map
            from Prompt 9. Add an alias to refer to a provider+model
            combination by short name in your specs.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {settings.modelAliases.length === 0 ? (
            <p className="rounded-md border border-dashed border-border/60 px-3 py-2 text-xs text-muted-foreground">
              No aliases yet. Click <strong>Add alias</strong> to create one.
            </p>
          ) : (
            settings.modelAliases.map((a, i) => (
              <div
                key={i}
                className="grid grid-cols-[1fr_1fr_2fr_auto] items-center gap-2"
              >
                <input
                  placeholder="alias"
                  value={a.alias}
                  onChange={(e) => updateAlias(i, { alias: e.target.value })}
                  className="rounded-md border border-input bg-background px-2.5 py-1.5 text-sm font-mono"
                />
                <select
                  value={a.provider}
                  onChange={(e) => updateAlias(i, { provider: e.target.value })}
                  className="rounded-md border border-input bg-background px-2.5 py-1.5 text-sm"
                >
                  {KNOWN_PROVIDERS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
                <input
                  placeholder="model id"
                  value={a.model}
                  onChange={(e) => updateAlias(i, { model: e.target.value })}
                  className="rounded-md border border-input bg-background px-2.5 py-1.5 text-sm font-mono"
                />
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label="Remove alias"
                  onClick={() => removeAlias(i)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))
          )}
          <Button type="button" variant="outline" size="sm" onClick={addAlias}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Add alias
          </Button>
        </CardContent>
      </Card>

      {/* ---------- Tracing ---------- */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Tracing</CardTitle>
          <CardDescription>
            Surface this run in LangSmith. The API key stays
            <strong className="ml-1">server-side</strong> — set
            <code className="mx-1 font-mono">LANGSMITH_API_KEY</code> on the
            backend env.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-input accent-primary"
              checked={settings.tracing.enabled}
              onChange={(e) =>
                update("tracing", { ...settings.tracing, enabled: e.target.checked })
              }
            />
            Send traces to LangSmith
          </label>
          <Field label="Project name">
            <input
              type="text"
              value={settings.tracing.project}
              onChange={(e) =>
                update("tracing", { ...settings.tracing, project: e.target.value })
              }
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
            />
          </Field>
        </CardContent>
      </Card>

      {/* ---------- Appearance ---------- */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Appearance</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Field label="Theme">
            <div className="flex gap-1.5">
              {(["light", "dark", "system"] as const).map((t) => (
                <Button
                  key={t}
                  type="button"
                  size="sm"
                  variant={theme === t ? "default" : "outline"}
                  onClick={() => setTheme(t)}
                >
                  {t}
                </Button>
              ))}
            </div>
          </Field>
          <Field label="Density">
            <div className="flex gap-1.5">
              {(["cozy", "compact"] as const).map((d) => (
                <Button
                  key={d}
                  type="button"
                  size="sm"
                  variant={settings.density === d ? "default" : "outline"}
                  onClick={() => update("density", d)}
                >
                  {d}
                </Button>
              ))}
            </div>
          </Field>
        </CardContent>
      </Card>

      <Separator />

      <div className="flex items-center gap-3">
        <Button type="submit">Save settings</Button>
        {saved ? <Badge variant="secondary">✓ saved</Badge> : null}
      </div>
    </form>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
      {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
    </label>
  );
}
