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
      sourceCount: 1,
      activeSourceCount: 1,
      errorSourceCount: 0,
      fallbackRequiredCount: 0,
      crawlCount: 4,
      lastFetchedAt: "2026-09-08T00:00:00Z",
      suggestionCount: 2,
      projectId: "project-1",
      pendingReviewCount: 1,
      approvedFactCount: 3,
      completeness: 75,
      sourceStatus: "active",
      affectedProjectCount: 2,
    },
  ],
  pendingReviewCount: 1,
  approvedFactCount: 3,
  sourceCount: 1,
  activeSourceCount: 1,
  crawlCount: 4,
  suggestionCount: 2,
  fallbackRequiredCount: 0,
  alerts: [],
};

const detail: PolicyCityDetailResponse = {
  cityId: "changsha",
  cityName: "长沙",
  documents: [],
  sourceCount: 1,
  activeSourceCount: 1,
  errorSourceCount: 0,
  fallbackRequiredCount: 0,
  crawlCount: 1,
  lastFetchedAt: "2026-09-08T00:00:00Z",
  suggestionCount: 2,
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
  it("surfaces browser fallback sources in the global overview", () => {
    render(
      <PolicyOverview
        initialData={{
          ...overview,
          cities: [
            {
              ...overview.cities[0],
              sourceStatus: "fallback_required",
              errorSourceCount: 1,
              activeSourceCount: 0,
              fallbackRequiredCount: 1,
            },
          ],
          fallbackRequiredCount: 1,
        }}
      />,
    );

    expect(screen.getByText("需浏览器通道")).toBeInTheDocument();
    expect(screen.getByText("需浏览器兜底")).toBeInTheDocument();
  });

  it("filters the global policy overview by city and shows crawler metrics", () => {
    const onCityChange = vi.fn();
    render(<PolicyOverview initialData={overview} onCityChange={onCityChange} />);

    expect(screen.getByRole("heading", { name: "政策资料" })).toBeInTheDocument();
    expect(screen.getByText("已配置来源 1")).toBeInTheDocument();
    expect(screen.getByText("待采用建议值 2")).toBeInTheDocument();
    expect(screen.getByText(/配置公开官网链接/)).toBeInTheDocument();
    expect(screen.queryByText(/上传城市政策/)).toBeNull();
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

  it("exposes policy exports from the city page", () => {
    render(<PolicyCityDetail data={detail} sources={detail.dataSources} artifacts={artifacts} />);

    expect(screen.getByRole("link", { name: "导出建议值 CSV" })).toHaveAttribute(
      "href",
      expect.stringContaining("/api/policies/export?format=csv&scope=city&cityId=changsha&dataset=fields"),
    );
    expect(screen.getByRole("link", { name: "导出抓取记录 CSV" })).toHaveAttribute(
      "href",
      expect.stringContaining("dataset=artifacts"),
    );
    expect(screen.getByRole("link", { name: "导出完整 JSON" })).toHaveAttribute(
      "href",
      expect.stringContaining("format=json"),
    );
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

  it("triggers a one-click crawl of all sources and shows the summary", async () => {
    const onCrawlAll = vi.fn().mockResolvedValue({
      cityId: "changsha",
      crawledAt: "2026-09-14T02:00:00Z",
      total: 2,
      succeeded: 1,
      failed: 1,
      skipped: 0,
      unchanged: 1,
      changed: 1,
      results: [
        {
          sourceId: "source-1",
          name: "长沙医保局",
          status: "success",
          changeStatus: "unchanged",
          httpStatus: 200,
          message: null,
        },
        {
          sourceId: "source-2",
          name: "长沙市统计局",
          status: "failed",
          changeStatus: null,
          httpStatus: null,
          message: "官网返回 HTTP 404，未保存内容",
        },
      ],
    });
    render(
      <PolicyCityDetail data={detail} sources={detail.dataSources} artifacts={[]} onCrawlAll={onCrawlAll} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /全部抓取/ }));
    await waitFor(() => expect(onCrawlAll).toHaveBeenCalledTimes(1));

    expect(await screen.findByText(/共 2 个来源/)).toBeInTheDocument();
    // 失败来源要逐条给出原因，而不是只报个数字
    expect(screen.getByText(/长沙市统计局：官网返回 HTTP 404/)).toBeInTheDocument();
  });

  it("flags stale sources from the freshness check", () => {
    render(
      <PolicyCityDetail
        data={detail}
        sources={detail.dataSources}
        artifacts={[]}
        freshness={{
          cityId: "changsha",
          checkedAt: "2026-09-14T02:00:00Z",
          staleDays: 365,
          agingDays: 180,
          counts: { total: 1, stale: 1, aging: 0, unknown: 0 },
          sources: [
            {
              sourceId: "source-1",
              name: "长沙医保局",
              url: "https://example.test",
              status: "active",
              lastFetchedAt: "2026-09-14T00:00:00Z",
              lastContentChangedAt: "2024-12-31T00:00:00Z",
              daysSinceChange: 621,
              looksAnnual: true,
              level: "stale",
              reason: "年度文档已 621 天无内容变更，可能已有新年度版本",
            },
          ],
        }}
      />,
    );

    // 汇总行点出有几个疑似过期
    expect(screen.getByText(/1 个疑似过期/)).toBeInTheDocument();
    // 逐条给出原因
    expect(screen.getByText(/长沙医保局：年度文档已 621 天无内容变更/)).toBeInTheDocument();
    // 来源行上挂徽标（文本恰好等于「疑似过期」的是 Badge）
    expect(screen.getByText("疑似过期")).toBeInTheDocument();
  });

  it("limits crawl history to the newest 30 with an expand toggle", () => {
    const many: CrawlArtifact[] = Array.from({ length: 35 }, (_, index) => ({
      ...artifacts[0],
      artifactId: `artifact-${index}`,
      title: `记录 ${index}`,
    }));
    render(<PolicyCityDetail data={detail} sources={detail.dataSources} artifacts={many} />);

    // 倒序渲染，最新（34）在前；第 20 条之后（14 及更早）默认不渲染
    expect(screen.getByText("记录 34")).toBeInTheDocument();
    expect(screen.getByText("记录 15")).toBeInTheDocument();
    expect(screen.queryByText("记录 14")).toBeNull();
    expect(screen.getByText(/共 35 条记录，当前只显示最新 20 条/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /展开全部/ }));
    expect(screen.getByText("记录 14")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "只看最新" })).toBeInTheDocument();
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
