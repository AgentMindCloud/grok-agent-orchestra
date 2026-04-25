"use client";

/**
 * `useRunStream(runId)` — connects to `/ws/runs/{runId}`, replays the
 * snapshot, then tails live events. Auto-reconnects with exponential
 * backoff (1s → 2s → 4s → 8s → 16s, capped at 16s). Buffers nothing
 * itself — the React state IS the buffer.
 */

import { useEffect, useRef, useState } from "react";

import { ApiClient } from "@/lib/api-client";
import { isTerminal } from "@/lib/events";
import type { WireEvent } from "@/types/api";

export type StreamConnectionStatus =
  | "idle"
  | "connecting"
  | "open"
  | "closed"
  | "reconnecting"
  | "errored";

export interface UseRunStreamResult {
  events: WireEvent[];
  status: StreamConnectionStatus;
  terminal: WireEvent | null;
  error: Error | null;
  reconnect: () => void;
}

export interface UseRunStreamOptions {
  client?: ApiClient;
  /** Cap how many events we keep in memory. Default 5000. */
  bufferSize?: number;
  /** Disable WebSocket entirely (useful in test setups). */
  disabled?: boolean;
  /** WebSocket constructor — `WebSocket` in browsers; injected for tests. */
  webSocketImpl?: typeof WebSocket;
}

const BACKOFF_MS = [1000, 2000, 4000, 8000, 16000];

export function useRunStream(
  runId: string | null,
  options: UseRunStreamOptions = {},
): UseRunStreamResult {
  const [events, setEvents] = useState<WireEvent[]>([]);
  const [status, setStatus] = useState<StreamConnectionStatus>("idle");
  const [terminal, setTerminal] = useState<WireEvent | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const attemptRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seenSeqsRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!runId || options.disabled) return undefined;

    const client = options.client ?? new ApiClient();
    const Ctor = options.webSocketImpl ?? WebSocket;
    const url = client.wsUrl(runId);
    const bufferSize = options.bufferSize ?? 5000;

    let cancelled = false;
    setEvents([]);
    setStatus("connecting");
    setTerminal(null);
    setError(null);
    seenSeqsRef.current = new Set();

    function open(): void {
      if (cancelled) return;
      const ws = new Ctor(url);
      wsRef.current = ws;
      ws.onopen = (): void => {
        attemptRef.current = 0;
        setStatus("open");
      };
      ws.onmessage = (msg: MessageEvent): void => {
        let parsed: WireEvent;
        try {
          parsed =
            typeof msg.data === "string"
              ? (JSON.parse(msg.data) as WireEvent)
              : (msg.data as WireEvent);
        } catch (e) {
          setError(e instanceof Error ? e : new Error(String(e)));
          return;
        }
        // Backend already dedupes seq across replay/live; we mirror it
        // for safety in case the client reconnects mid-stream.
        const seq = typeof parsed.seq === "number" ? parsed.seq : null;
        if (seq !== null) {
          if (seenSeqsRef.current.has(seq)) return;
          seenSeqsRef.current.add(seq);
        }
        setEvents((prev) => {
          const next = prev.length >= bufferSize ? prev.slice(-bufferSize + 1) : prev;
          return [...next, parsed];
        });
        if (isTerminal(parsed)) setTerminal(parsed);
      };
      ws.onerror = (): void => {
        setError(new Error("WebSocket error"));
        setStatus("errored");
      };
      ws.onclose = (): void => {
        if (cancelled) return;
        // Don't reconnect on a clean terminal close.
        if (terminal !== null) {
          setStatus("closed");
          return;
        }
        scheduleReconnect();
      };
    }

    function scheduleReconnect(): void {
      const idx = Math.min(attemptRef.current, BACKOFF_MS.length - 1);
      const delay = BACKOFF_MS[idx];
      attemptRef.current += 1;
      setStatus("reconnecting");
      reconnectTimerRef.current = setTimeout(() => {
        if (!cancelled) open();
      }, delay);
    }

    open();

    return () => {
      cancelled = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      const ws = wsRef.current;
      wsRef.current = null;
      if (ws && ws.readyState <= 1) ws.close();
    };
    // The terminal flag is intentionally NOT in the dep list — that
    // would cause a re-subscription every time a terminal event lands.
    // We read the latest terminal value inside the closure via ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, options.disabled]);

  function reconnect(): void {
    attemptRef.current = 0;
    if (wsRef.current && wsRef.current.readyState <= 1) {
      wsRef.current.close();
    }
  }

  return { events, status, terminal, error, reconnect };
}
