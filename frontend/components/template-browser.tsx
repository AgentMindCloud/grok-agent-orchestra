"use client";

import { useState } from "react";
import useSWR from "swr";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { api } from "@/lib/api-client";
import { setSelectedTemplate } from "@/lib/selection-store";
import { cn } from "@/lib/utils";
import type { TemplateDetail, TemplatesListResponse } from "@/types/api";

const listFetcher = async (): Promise<TemplatesListResponse> =>
  api.listTemplates();
const detailFetcher = async (key: string): Promise<TemplateDetail> => {
  const name = key.split(":").pop() as string;
  return api.getTemplate(name);
};

export function TemplateBrowser(): JSX.Element {
  const [active, setActive] = useState<string | null>(null);
  const { data: list } = useSWR<TemplatesListResponse>(
    "/api/templates",
    listFetcher,
  );
  const { data: detail } = useSWR<TemplateDetail | null>(
    active ? `template:${active}` : null,
    detailFetcher,
  );

  if (!list) return <div className="h-72 animate-pulse rounded-md bg-muted" />;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
      <ul className="space-y-1">
        {list.templates.map((tpl) => (
          <li key={tpl.name}>
            <button
              type="button"
              onClick={() => setActive(tpl.name)}
              className={cn(
                "w-full rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-muted",
                active === tpl.name && "bg-muted font-medium",
              )}
            >
              {tpl.name}
              <span className="ml-2 text-xs text-muted-foreground">
                {tpl.category}
              </span>
            </button>
          </li>
        ))}
      </ul>

      <div>
        {!active || !detail ? (
          <Card>
            <CardHeader>
              <CardTitle>Select a template</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Click a template on the left to see its YAML and tags.
              </p>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0">
              <div>
                <CardTitle>{detail.name}</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  {detail.description}
                </p>
              </div>
              <Button
                onClick={() => setSelectedTemplate(detail.name)}
                size="sm"
              >
                Use on dashboard
              </Button>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-1">
                {detail.tags.map((t) => (
                  <Badge key={t} variant="secondary">
                    {t}
                  </Badge>
                ))}
              </div>
              <pre className="max-h-[55vh] overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-xs leading-relaxed">
                {detail.yaml}
              </pre>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
