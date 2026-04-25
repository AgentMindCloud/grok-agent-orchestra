"use client";

/**
 * Coalesces a high-frequency event stream into ~60fps batches via
 * `requestAnimationFrame`. The backend fires hundreds of token events
 * per second on hot prompts; rendering each one synchronously triggers
 * scheduling pressure and dropped frames. We accept the small per-frame
 * latency in exchange for buttery 60fps.
 *
 * Falls back to `setTimeout(0)` outside the browser (vitest's
 * happy-dom does support rAF, but server-rendered first paint must
 * never call rAF).
 */

import { useEffect, useState } from "react";

import type { WireEvent } from "@/types/api";

export function useBatchedEvents(events: WireEvent[]): WireEvent[] {
  const [batched, setBatched] = useState<WireEvent[]>(events);

  useEffect(() => {
    if (typeof window === "undefined") {
      setBatched(events);
      return;
    }
    if (events.length === batched.length) return;
    let raf = 0;
    const schedule =
      typeof window.requestAnimationFrame === "function"
        ? (cb: FrameRequestCallback) => window.requestAnimationFrame(cb)
        : (cb: (t: number) => void) => window.setTimeout(() => cb(performance.now()), 16);
    const cancel =
      typeof window.cancelAnimationFrame === "function"
        ? (h: number) => window.cancelAnimationFrame(h)
        : (h: number) => window.clearTimeout(h);

    raf = schedule(() => setBatched(events));
    return () => cancel(raf);
  }, [events, batched.length]);

  return batched;
}
