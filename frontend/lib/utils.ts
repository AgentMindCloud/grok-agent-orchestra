import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * shadcn-conventional className helper. Composes `clsx` + `twMerge`
 * so conflicting Tailwind classes (e.g. `p-2 p-4`) collapse to the
 * winning rule.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
