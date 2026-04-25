"use client";

/**
 * Debate visualisation entry point.
 *
 * Composes the three role lanes (Harper / Benjamin / Grok) into a
 * horizontal grid on desktop; collapses to a tab switcher on mobile.
 * Lucas is rendered separately by the page-level layout — it's the
 * judge bench, not a lane.
 */

import { useMemo } from "react";

import { RoleAvatar } from "@/components/role-avatar";
import { RoleLane } from "@/components/role-lane";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { TooltipProvider } from "@/components/ui/tooltip";
import { LANE_ROLES, roleMeta } from "@/lib/role-meta";
import type { StreamModel } from "@/lib/use-stream-model";
import { cn } from "@/lib/utils";

interface DebateStreamProps {
  model: StreamModel;
  className?: string;
}

export function DebateStream({ model, className }: DebateStreamProps): JSX.Element {
  // Default the mobile tab to whichever lane has an active speaker —
  // lets you open a fresh view straight onto the action.
  const initialTab = useMemo(() => {
    for (const role of LANE_ROLES) {
      if (model.lanes[role].openMessageId) return role;
    }
    return LANE_ROLES[0];
  }, [model.lanes]);

  return (
    <TooltipProvider delayDuration={200}>
      {/* Desktop: 3-up horizontal lanes */}
      <div
        className={cn(
          "hidden gap-3 lg:grid lg:grid-cols-3",
          className,
        )}
      >
        {LANE_ROLES.map((role) => (
          <RoleLane key={role} lane={model.lanes[role]} />
        ))}
      </div>

      {/* Mobile / tablet: tabs */}
      <Tabs
        defaultValue={initialTab}
        className={cn("lg:hidden", className)}
      >
        <TabsList className="grid w-full grid-cols-3">
          {LANE_ROLES.map((role) => {
            const meta = roleMeta(role);
            const isActive = model.lanes[role].openMessageId !== null;
            return (
              <TabsTrigger key={role} value={role} className="gap-2">
                <RoleAvatar role={role} size="sm" active={isActive} />
                <span className={cn("hidden sm:inline", meta.textClass)}>{meta.name}</span>
              </TabsTrigger>
            );
          })}
        </TabsList>
        {LANE_ROLES.map((role) => (
          <TabsContent key={role} value={role}>
            <RoleLane lane={model.lanes[role]} />
          </TabsContent>
        ))}
      </Tabs>
    </TooltipProvider>
  );
}
