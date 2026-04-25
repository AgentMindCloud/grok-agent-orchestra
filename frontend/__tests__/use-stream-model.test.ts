import { describe, expect, it } from "vitest";

import { buildModel } from "@/lib/use-stream-model";
import type { WireEvent } from "@/types/api";

const ev = (e: WireEvent): WireEvent => e;

describe("buildModel — lane reducer", () => {
  it("opens a message on role_started and accumulates tokens", () => {
    const events: WireEvent[] = [
      ev({ type: "role_started", role: "Harper", seq: 1 }),
      ev({ type: "stream", kind: "token", role: "Harper", text: "hello ", seq: 2 }),
      ev({ type: "stream", kind: "token", role: "Harper", text: "world", seq: 3 }),
    ];
    const m = buildModel(events);
    expect(m.lanes.Harper.messages).toHaveLength(1);
    expect(m.lanes.Harper.messages[0].text).toBe("hello world");
    expect(m.lanes.Harper.messages[0].status).toBe("streaming");
    expect(m.lanes.Harper.openMessageId).not.toBeNull();
  });

  it("closes the message on role_completed and counts citations", () => {
    const events: WireEvent[] = [
      ev({ type: "role_started", role: "Harper", seq: 1 }),
      ev({
        type: "role_completed",
        role: "Harper",
        output:
          "found a fact [web:example.com] and a backup [web:other.org].",
        seq: 9,
      }),
    ];
    const m = buildModel(events);
    const msg = m.lanes.Harper.messages[0];
    expect(msg.status).toBe("done");
    expect(msg.text).toContain("found a fact");
    expect(msg.citationCount).toBe(2);
    expect(m.lanes.Harper.totalCitations).toBe(2);
    expect(m.lanes.Harper.openMessageId).toBeNull();
  });

  it("attaches tool calls + results to the open message", () => {
    const events: WireEvent[] = [
      ev({ type: "role_started", role: "Harper", seq: 1 }),
      ev({
        type: "stream",
        kind: "tool_call",
        role: "Harper",
        tool_name: "web_search",
        tool_args: { q: "agentic ai 2026" },
        seq: 2,
      }),
      ev({
        type: "stream",
        kind: "tool_result",
        role: "Harper",
        tool_name: "web_search",
        result: ["a", "b", "c"],
        seq: 3,
      }),
      ev({ type: "role_completed", role: "Harper", output: "done.", seq: 4 }),
    ];
    const m = buildModel(events);
    const msg = m.lanes.Harper.messages[0];
    expect(msg.toolCalls).toHaveLength(1);
    expect(msg.toolCalls[0].toolName).toBe("web_search");
    expect(msg.toolCalls[0].status).toBe("ok");
    expect(msg.toolCalls[0].result).toContain("a");
  });

  it("synthesises a message when tokens arrive without a role_started", () => {
    const events: WireEvent[] = [
      ev({
        type: "stream",
        kind: "token",
        role: "Benjamin",
        text: "implicit start",
        seq: 1,
      }),
    ];
    const m = buildModel(events);
    expect(m.lanes.Benjamin.messages).toHaveLength(1);
    expect(m.lanes.Benjamin.messages[0].text).toBe("implicit start");
  });
});

describe("buildModel — Lucas state", () => {
  it("captures a passed verdict with confidence", () => {
    const events: WireEvent[] = [
      ev({ type: "role_started", role: "Grok", seq: 1 }),
      ev({ type: "role_completed", role: "Grok", output: "synthesis", seq: 2 }),
      ev({ type: "lucas_passed", confidence: 0.92, seq: 3 }),
    ];
    const m = buildModel(events);
    expect(m.lucas.status).toBe("passed");
    expect(m.lucas.confidence).toBe(0.92);
    expect(m.lucas.verdicts).toHaveLength(1);
    expect(m.lucas.verdicts[0].kind).toBe("passed");
  });

  it("flags the most recent message as vetoed when Lucas vetos", () => {
    const events: WireEvent[] = [
      ev({ type: "role_started", role: "Grok", seq: 1 }),
      ev({
        type: "role_completed",
        role: "Grok",
        output: "controversial draft",
        seq: 2,
      }),
      ev({
        type: "lucas_veto",
        reason: "could be read as fearmongering",
        blocked_content: "controversial draft",
        seq: 3,
      }),
    ];
    const m = buildModel(events);
    expect(m.lucas.status).toBe("vetoed");
    const grokMsg = m.lanes.Grok.messages[0];
    expect(grokMsg.status).toBe("vetoed");
    expect(m.lucas.vetoedMessageIds.has(grokMsg.id)).toBe(true);
  });

  it("never crashes on an empty event list", () => {
    const m = buildModel([]);
    expect(m.lucas.status).toBe("idle");
    expect(m.round).toBe(0);
    expect(m.finalOutput).toBeNull();
  });

  it("captures the terminal final_output", () => {
    const events: WireEvent[] = [
      ev({ type: "role_started", role: "Grok", seq: 1 }),
      ev({ type: "role_completed", role: "Grok", output: "the answer", seq: 2 }),
      ev({ type: "run_completed", final_output: "shipped synthesis", seq: 9 }),
    ];
    const m = buildModel(events);
    expect(m.finalOutput).toBe("shipped synthesis");
    expect(m.lucas.status).toBe("passed"); // implicit pass on completion
  });

  it("records failure reason on run_failed", () => {
    const events: WireEvent[] = [
      ev({ type: "run_failed", error: "rate limited", seq: 1 }),
    ];
    const m = buildModel(events);
    expect(m.failureReason).toBe("rate limited");
  });
});

describe("buildModel — debate rounds", () => {
  it("tracks the round_n high-water mark", () => {
    const events: WireEvent[] = [
      ev({ type: "debate_round_started", round_n: 1, seq: 1 }),
      ev({ type: "debate_round_started", round_n: 2, seq: 2 }),
      ev({ type: "debate_round_started", round_n: 3, seq: 3 }),
    ];
    const m = buildModel(events);
    expect(m.round).toBe(3);
  });
});
