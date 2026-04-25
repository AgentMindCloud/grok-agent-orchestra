import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError, resolveBaseUrl, resolveWsUrl } from "@/lib/api-client";

function jsonResponse<T>(body: T, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("resolveBaseUrl", () => {
  it("strips trailing slashes", () => {
    expect(resolveBaseUrl({ baseUrl: "http://x:8000///" })).toBe("http://x:8000");
  });
  it("falls back to NEXT_PUBLIC_API_URL", () => {
    process.env.NEXT_PUBLIC_API_URL = "http://env-default:9000";
    try {
      expect(resolveBaseUrl()).toBe("http://env-default:9000");
    } finally {
      delete process.env.NEXT_PUBLIC_API_URL;
    }
  });
});

describe("resolveWsUrl", () => {
  it("swaps http → ws", () => {
    expect(resolveWsUrl({ baseUrl: "http://localhost:8000" })).toBe(
      "ws://localhost:8000",
    );
  });
  it("swaps https → wss", () => {
    expect(resolveWsUrl({ baseUrl: "https://prod.example.com" })).toBe(
      "wss://prod.example.com",
    );
  });
  it("honours NEXT_PUBLIC_WS_URL when set", () => {
    process.env.NEXT_PUBLIC_WS_URL = "wss://override:9999/";
    try {
      expect(resolveWsUrl()).toBe("wss://override:9999");
    } finally {
      delete process.env.NEXT_PUBLIC_WS_URL;
    }
  });
});

describe("ApiClient", () => {
  it("calls /api/health and parses the typed response", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo) => {
      expect(String(url)).toBe("http://api.test/api/health");
      return jsonResponse({ status: "ok", version: "0.1.0" });
    });
    const client = new ApiClient({ baseUrl: "http://api.test", fetch: fetchMock as typeof fetch });
    const out = await client.health();
    expect(out).toEqual({ status: "ok", version: "0.1.0" });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("startRun POSTs JSON and returns run_id", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo, init?: RequestInit) => {
      expect(String(url)).toBe("http://api.test/api/run");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(String(init?.body ?? "{}"));
      expect(body.simulated).toBe(true);
      expect(body.yaml).toContain("name: tpl");
      return jsonResponse({ run_id: "abc123" });
    });
    const client = new ApiClient({
      baseUrl: "http://api.test",
      fetch: fetchMock as typeof fetch,
    });
    const out = await client.startRun({
      yaml: "name: tpl\ngoal: hi",
      simulated: true,
    });
    expect(out.run_id).toBe("abc123");
  });

  it("throws ApiError with detail on 4xx", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ detail: "missing yaml" }, 422),
    );
    const client = new ApiClient({ baseUrl: "http://api.test", fetch: fetchMock as typeof fetch });
    await expect(client.validate({ yaml: "" })).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
      detail: "missing yaml",
    });
  });

  it("reportUrl + wsUrl compose the expected paths", () => {
    const client = new ApiClient({ baseUrl: "http://localhost:8000" });
    expect(client.reportUrl("r1", "pdf")).toBe(
      "http://localhost:8000/api/runs/r1/report.pdf",
    );
    expect(client.wsUrl("r1")).toBe("ws://localhost:8000/ws/runs/r1");
  });

  it("ApiError exposes name + status + detail", () => {
    const err = new ApiError(500, "POST /api/run → 500", "boom");
    expect(err.name).toBe("ApiError");
    expect(err.status).toBe(500);
    expect(err.detail).toBe("boom");
    expect(err.message).toContain("/api/run");
  });
});
