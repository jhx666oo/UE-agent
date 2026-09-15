import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PolicyResearchRunCard } from "./policy-research-run-card";
import type { PolicyResearchRun } from "@/lib/policies";

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  retry: vi.fn(),
}));

vi.mock("@/lib/policies", () => ({
  createPolicyResearchRun: mocks.create,
  retryPolicyResearchRun: mocks.retry,
}));

afterEach(() => {
  cleanup();
  mocks.create.mockReset();
  mocks.retry.mockReset();
});

const queuedRun: PolicyResearchRun = {
  id: "research-1",
  cityId: "长沙",
  projectId: null,
  trigger: "ui",
  scope: "all",
  fields: [],
  status: "queued",
  phase: "queued",
  agentRunId: null,
  agentVersion: null,
  queryCount: 3,
  sourceCount: 0,
  newSourceCount: 0,
  changedSourceCount: 0,
  fetchedCount: 0,
  suggestionCount: 0,
  errorCount: 0,
  errors: [],
  taskPrompt: "请执行长沙政策实时检索，完成后回传 research-1。",
  requestedAt: "2026-09-15T00:00:00Z",
  startedAt: null,
  finishedAt: null,
  createdAt: "2026-09-15T00:00:00Z",
  updatedAt: "2026-09-15T00:00:00Z",
};

describe("PolicyResearchRunCard", () => {
  it("从城市政策页发起实时检索并展示排队提示", async () => {
    mocks.create.mockResolvedValue(queuedRun);

    render(<PolicyResearchRunCard cityId="长沙" cityName="长沙" />);

    fireEvent.click(screen.getByRole("button", { name: "AI 实时更新政策" }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith({
      cityId: "长沙",
      trigger: "ui",
      scope: "all",
    }));
    expect(await screen.findByText("等待 WorkBuddy 执行")).toBeInTheDocument();
    expect(screen.getByText("任务已排队")).toBeInTheDocument();
    expect(screen.getByText(queuedRun.taskPrompt ?? "")).toBeInTheDocument();
  });

  it("失败任务可以从页面重新排队", async () => {
    const failedRun = { ...queuedRun, status: "failed" as const, phase: "failed", errors: ["检索服务暂时不可用"] };
    const retriedRun = { ...queuedRun, status: "queued" as const };
    mocks.retry.mockResolvedValue(retriedRun);

    render(<PolicyResearchRunCard cityId="长沙" cityName="长沙" initialRun={failedRun} />);

    expect(screen.getByText("需要重试")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新排队" }));

    await waitFor(() => expect(mocks.retry).toHaveBeenCalledWith("research-1"));
    expect(await screen.findByText("等待 WorkBuddy 执行")).toBeInTheDocument();
  });

  it("历史任务完成后仍可以发起下一轮更新", async () => {
    const completedRun = { ...queuedRun, status: "completed" as const, phase: "completed" };
    mocks.create.mockResolvedValue({ ...queuedRun, id: "research-2" });

    render(<PolicyResearchRunCard cityId="长沙" cityName="长沙" initialRun={completedRun} />);

    fireEvent.click(screen.getByRole("button", { name: "再次更新政策" }));

    await waitFor(() => expect(mocks.create).toHaveBeenCalledWith({
      cityId: "长沙",
      trigger: "ui",
      scope: "all",
    }));
    expect(await screen.findByText("等待 WorkBuddy 执行")).toBeInTheDocument();
  });
});
