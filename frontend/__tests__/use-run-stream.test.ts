import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useRunStream } from "@/lib/use-run-stream";

// Minimal in-memory WebSocket stub. Implements the surface
// `useRunStream` actually uses: `onopen`, `onmessage`, `onerror`,
// `onclose`, `close`, `readyState`. Behaves like the real thing
// enough to drive the hook's state machine deterministically.

class FakeWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  url: string;
  readyState = 0;
  onopen: ((ev?: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev?: Event) => void) | null = null;
  onclose: ((ev?: CloseEvent) => void) | null = null;
  static instances: FakeWebSocket[] = [];

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => {
      this.readyState = FakeWebSocket.OPEN;
      this.onopen?.();
    });
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  emit(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }

  emitError(): void {
    this.onerror?.();
  }
}

describe("useRunStream", () => {
  it("connects, accumulates events, and notes the terminal frame", async () => {
    FakeWebSocket.instances = [];
    const { result } = renderHook(() =>
      useRunStream("run-1", {
        webSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
      }),
    );

    await waitFor(() => expect(result.current.status).toBe("open"));

    const ws = FakeWebSocket.instances[0];
    expect(ws.url).toContain("/ws/runs/run-1");

    act(() => {
      ws.emit({ type: "snapshot_begin", run: { id: "run-1" } });
      ws.emit({
        type: "stream",
        kind: "token",
        role: "Harper",
        text: "looking",
        seq: 1,
      });
      ws.emit({ type: "snapshot_end" });
      ws.emit({ type: "run_completed", final_output: "done", seq: 9 });
    });

    await waitFor(() => expect(result.current.terminal).toBeTruthy());
    expect(result.current.events.length).toBe(4);
    expect(result.current.terminal?.type).toBe("run_completed");
  });

  it("dedupes events by seq across reconnects", async () => {
    FakeWebSocket.instances = [];
    const { result } = renderHook(() =>
      useRunStream("run-2", {
        webSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
      }),
    );
    await waitFor(() => expect(result.current.status).toBe("open"));

    const ws = FakeWebSocket.instances[0];
    act(() => {
      ws.emit({ type: "stream", kind: "token", text: "a", seq: 1 });
      ws.emit({ type: "stream", kind: "token", text: "a", seq: 1 }); // dupe
      ws.emit({ type: "stream", kind: "token", text: "b", seq: 2 });
    });
    await waitFor(() => expect(result.current.events.length).toBe(2));
  });

  it("does nothing when runId is null", () => {
    const { result } = renderHook(() =>
      useRunStream(null, {
        webSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
      }),
    );
    expect(result.current.status).toBe("idle");
    expect(result.current.events).toEqual([]);
  });
});
