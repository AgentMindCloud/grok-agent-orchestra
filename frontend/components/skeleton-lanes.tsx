"use client";

import { RoleAvatar } from "@/components/role-avatar";
import { Skeleton } from "@/components/ui/skeleton";
import { LANE_ROLES, roleMeta } from "@/lib/role-meta";
import { cn } from "@/lib/utils";

export function SkeletonLanes(): JSX.Element {
  return (
    <div className="grid gap-3 lg:grid-cols-3" aria-busy="true" aria-label="Loading debate stream">
      {LANE_ROLES.map((role) => {
        const meta = roleMeta(role);
        return (
          <div
            key={role}
            className={cn(
              "flex h-[40vh] flex-col gap-3 rounded-lg border p-3",
              meta.laneClass,
            )}
          >
            <div className="flex items-center gap-2.5">
              <RoleAvatar role={role} />
              <div>
                <p className={cn("text-sm font-semibold", meta.textClass)}>{meta.name}</p>
                <p className="text-[11px] text-muted-foreground">{meta.oneLine}</p>
              </div>
            </div>
            <Skeleton className="h-16" />
            <Skeleton className="h-12 w-3/4" />
            <Skeleton className="h-20" />
          </div>
        );
      })}
    </div>
  );
}
