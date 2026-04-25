"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { RoleName } from "@/lib/events";
import { roleMeta } from "@/lib/role-meta";
import { cn } from "@/lib/utils";

interface RoleAvatarProps {
  role: RoleName;
  size?: "sm" | "md" | "lg";
  active?: boolean;
}

export function RoleAvatar({
  role,
  size = "md",
  active = false,
}: RoleAvatarProps): JSX.Element {
  const meta = roleMeta(role);
  const sizeClass =
    size === "lg" ? "h-10 w-10 text-base" : size === "sm" ? "h-6 w-6 text-[11px]" : "h-8 w-8 text-sm";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex select-none items-center justify-center rounded-full font-semibold ring-2 ring-offset-2 ring-offset-background",
            sizeClass,
            meta.ringClass,
            meta.bgClass,
            meta.textClass,
            active && "shadow-[0_0_0_2px_hsl(var(--ring))] motion-safe:animate-pulse",
          )}
          aria-label={`${meta.name} — ${meta.oneLine}`}
        >
          {meta.glyph}
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        <div className="space-y-1">
          <p className="font-semibold">
            {meta.name} <span className="text-muted-foreground">· {meta.oneLine}</span>
          </p>
          <p className="text-muted-foreground">{meta.description}</p>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
