import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PolicyCityDetail } from "./policy-city-detail";
import { PolicyOverview } from "./policy-overview";
import type { CrawlArtifact, PolicyCityDetailResponse, PolicyOverviewResponse } from "@/lib/policies";

const overview: PolicyOverviewResponse = {
  cities: [
    {
      cityId: "changsha",
      cityName: "长沙",
      documentCount: 2,
      latestUpdatedAt: "2026-09-08T00:00:00Z",
      pendingReviewCount: 1,
      approvedFactCount: 3,
      completeness: 75,
      sourceStatus: "active",
      affectedProjectCount: 2,
    },
  ],
  pendingReviewCount: 1,
  approvedFactCount: 3,
  alerts: [],
};

const detail: PolicyCityDetailResponse = {
  cityId: "changsha",
  cityName: "长沙",
  documents: [],
  dataSources: [
    { id: "source-1", cityId: "changsha", name: "长沙医保局", kind: "government", url: "https://example.test", status: "active", createdAt: "2026-09-08T00:00:00Z", updatedAt: "2026-09-08T00:00:00Z" },
  ],
  facts: [],
  approvedFacts: [],
  pendingReviewCount: 0,
  projects: [{ id: "project-1", name: "长沙项目" }],
};

const artifacts: CrawlArtifact[] = [
  {
    artifactId: "artifact-1",
    sourceId: "source-1",
    cityId: "changsha",
    requestedUrl: "https://example.test/policy",
    finalUrl: "https://example.test/policy",
    fetchedAt: "2026-09-08T00:00:00Z",
    httpStatus: 200,
    contentType: "text/html; charset=utf-8",
    contentLength: 1234,
    sha256: "abc",
    storedPath: "raw_sources/abc.bin",
    title: "长期护理保险政策",
    changeStatus: "first_fetch",
    status: "success",
    errorMessage: null,
    suggestions: [
      { fieldId: "P1", name: "单小时服务单价", value: 60, quote: "单小时服务单价为 60 元" },
      { fieldId: "P2", name: "基金支付比例", value: 0.8, quote: "基金支付比例 80%" },
    ],
  },
  {
    artifactId: "artifact-2",
    sourceId: "source-1",
    cityId: "changsha",
    requestedUrl: "https://example.test/policy",
    finalUrl: null,
    fetchedAt: "2026-09-09T00:00:00Z",
    httpStatus: null,
    contentType: null,
    contentLength: null,
    sha256: null,
    storedPath: null,
    title: null,
    changeStatus: null,
    status: "failed",
    errorMessage: "官网抓取超时，请稍后重试或调整超时设置",
  },
];

afterEach(() => cleanup());

describe("policy center", () => {
  it("filters the global policy overview by city and shows review badges", () => {
    const onCityChange = vi.fn();
    render(<PolicyOverview initialData={overview} onCityChange={onCityChange} />);

    expect(screen.getByRole("heading", { name: "政策资料" })).toBeInTheDocument();
    expect(screen.getByText("待审核 1")).toBeInTheDocument();
    expect(screen.getByText("已确认 3")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("城市"), { target: { value: "changsha" } });
    expect(onCityChange).toHaveBeenCalledWith("changsha");
  });

  it("renders empty policy guidance", () => {
    render(<PolicyOverview initialData={{ ...overview, cities: [], pendingReviewCount: 0, approvedFactCount: 0 }} />);
    expect(screen.getByText("暂无政策资料")).toBeInTheDocument();
  });

  it("shows source config, crawl history with suggestions and keeps inputs safe", () => {
    render(
      <PolicyCityDetail
        data={detail}
        sources={detail.dataSources}
        artifacts={artifacts}
      />,
    );

    // 来源列表带状态与最近抓取信息
    expect(screen.getByText("长沙医保局")).toBeInTheDocument();
    // 抓取历史：成功记录显示标题、指纹状态与建议值，失败记录保留原因
    expect(screen.getByText("长期护理保险政策")).toBeInTheDocument();
    expect(screen.getByText("首次抓取")).toBeInTheDocument();
    expect(screen.getByText(/P1=60/)).toBeInTheDocument();
    expect(screen.getByText(/P2=0.8/)).toBeInTheDocument();
    expect(screen.getByText(/官网抓取超时/)).toBeInTheDocument();
    // 不会自动覆盖参数的提示
    expect(
      screen.getByText(
        "建议值以灰色提示展示在城市测算页，点击「采用建议值」后才写入参数；手工填写会标记为已覆盖并保留建议值来源。",
      ),
    ).toBeInTheDocument();
  });

  it("triggers a crawl from the source row", async () => {
    const onCrawl = vi.fn().mockResolvedValue(undefined);
    render(
      <PolicyCityDetail
        data={detail}
        sources={detail.dataSources}
        artifacts={[]}
        onCrawl={onCrawl}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "立即抓取" }));
    await waitFor(() => expect(onCrawl).toHaveBeenCalledWith(detail.dataSources[0]));
  });

  it("creates a new source from the form", async () => {
    const onCreateSource = vi.fn().mockResolvedValue(undefined);
    render(
      <PolicyCityDetail
        data={detail}
        sources={[]}
        artifacts={[]}
        onCreateSource={onCreateSource}
      />,
    );

    fireEvent.change(screen.getByLabelText("来源名称"), { target: { value: "长沙民政局" } });
    fireEvent.change(screen.getByLabelText("官网链接"), { target: { value: "https://mzj.example.gov.cn" } });
    fireEvent.click(screen.getByRole("button", { name: /新增来源/ }));

    await waitFor(() =>
      expect(onCreateSource).toHaveBeenCalledWith({
        name: "长沙民政局",
        url: "https://mzj.example.gov.cn",
      }),
    );
  });

  it("disables crawl for a paused source and offers re-enabling", async () => {
    const onToggleSource = vi.fn().mockResolvedValue(undefined);
    const paused = [{ ...detail.dataSources[0], status: "paused" as const }];
    render(
      <PolicyCityDetail
        data={detail}
        sources={paused}
        artifacts={[]}
        onToggleSource={onToggleSource}
      />,
    );

    expect(screen.getByRole("button", { name: "立即抓取" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "启用" }));
    await waitFor(() => expect(onToggleSource).toHaveBeenCalledWith(paused[0]));
  });
});
