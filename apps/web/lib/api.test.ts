import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch, buildApiUrl, deleteProject, formatFormulaValue } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("U1 API client", () => {
  it("joins an API base URL without duplicating slashes", () => {
    expect(buildApiUrl("/api/health", "http://localhost:8000/")).toBe("http://localhost:8000/api/health");
    expect(buildApiUrl("api/health", "http://localhost:8000")).toBe("http://localhost:8000/api/health");
  });

  it("turns a structured API error into a useful exception", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "项目不存在" } }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(apiFetch("/api/projects/missing")).rejects.toThrow("项目不存在");
  });

  it("keeps zero distinct from blank and formula errors", () => {
    expect(formatFormulaValue({ value: 0, status: "ok", errorCode: null })).toBe("0");
    expect(formatFormulaValue({ value: null, status: "ok", errorCode: null })).toBe("未计算");
    expect(formatFormulaValue({ value: null, status: "formula_error", errorCode: "DIV0" })).toBe("不可计算：DIV0");
  });

  it("sends DELETE for project removal and returns the deletion receipt", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ deleted: true, projectId: "proj-1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(deleteProject("proj-1")).resolves.toEqual({ deleted: true, projectId: "proj-1" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/projects/proj-1");
    expect(init.method).toBe("DELETE");
  });

  it("surfaces the stable NOT_FOUND code when deleting an unknown project", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "NOT_FOUND", message: "Project not found: gone" } }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(deleteProject("gone")).rejects.toMatchObject({ code: "NOT_FOUND" });
  });
});
