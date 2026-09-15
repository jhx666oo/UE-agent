import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it } from "vitest";
import { CityOnboardingStatus } from "./city-onboarding-status";
import type { CityOnboardingJob } from "@/lib/api";

const baseJob: CityOnboardingJob = {
  id: "job-1",
  projectId: "project-1",
  cityId: "chengdu",
  cityName: "成都",
  status: "crawling",
  phase: "crawling",
  totalQueries: 3,
  discoveredCount: 4,
  officialSourceCount: 2,
  candidateCount: 2,
  crawledCount: 1,
  suggestionCount: 0,
  errorCount: 0,
  errors: [],
  startedAt: null,
  finishedAt: null,
  createdAt: "2026-09-15T00:00:00Z",
  updatedAt: "2026-09-15T00:00:00Z",
};

afterEach(() => cleanup());

describe("CityOnboardingStatus", () => {
  it("shows source discovery progress and suggestion count", () => {
    render(<CityOnboardingStatus projectId="project-1" initialJob={baseJob} poll={false} />);

    expect(screen.getByText(/正在抓取成都/)).toBeInTheDocument();
    expect(screen.getByText(/已发现 4 个来源/)).toBeInTheDocument();
    expect(screen.getByText(/正式来源 2 个/)).toBeInTheDocument();
    expect(screen.getByText(/候选来源 2 个/)).toBeInTheDocument();
  });

  it("explains partial failure without blocking measurement", () => {
    render(
      <CityOnboardingStatus
        projectId="project-1"
        initialJob={{
          ...baseJob,
          status: "partial_failed",
          phase: "partial_failed",
          errorCount: 1,
          errors: ["统计局来源暂时不可达"],
        }}
        poll={false}
      />,
    );

    expect(screen.getByText(/部分完成/)).toBeInTheDocument();
    expect(screen.getByText(/仍可继续填写和运行测算/)).toBeInTheDocument();
    expect(screen.getByText("统计局来源暂时不可达")).toBeInTheDocument();
  });
});
