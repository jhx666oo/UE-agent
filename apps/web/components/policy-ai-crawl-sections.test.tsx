import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PolicyCrawlStatusSection,
  PolicyExtractionResultSection,
  PolicySourceCandidateSection,
} from "./policy-ai-crawl-sections";
import type {
  CrawlTargetsResponse,
  ExtractionSubmissionRecord,
  SourceCandidate,
} from "@/lib/policies";

afterEach(cleanup);

const targets: CrawlTargetsResponse = {
  generatedAt: "2026-09-11T00:00:00Z",
  readScope: "configured_sources_plus_ai_discovery",
  fieldCatalog: [
    { id: "P1", name: "单小时服务单价", unit: "元/小时", valueType: "number", options: null, block: "政策准入", difficulty: "A", neverEstimate: false },
    { id: "C2", name: "城市行政等级", unit: "-", valueType: "string", options: ["一线", "新一线", "二线", "三线"], block: "城市与市场", difficulty: "B", neverEstimate: false },
    { id: "C6", name: "失能率_60-69岁", unit: "%", valueType: "number", options: null, block: "城市与市场", difficulty: "D", neverEstimate: true },
  ],
  fieldFamilies: [
    { family: "政策准入", queryTemplate: "{城市} 长期护理保险 实施办法", fields: ["P1"], sourceHint: "医保局政策文件" },
  ],
  difficultyLevels: { A: "政策文本可直接读到数值", B: "需归一化到枚举值", C: "统计公报数据", D: "官方无公开数据，禁止估算" },
  neverEstimateFields: ["C6"],
  cities: [
    {
      cityId: "changsha",
      cityName: "长沙",
      sources: [
        {
          sourceId: "source-1",
          name: "长沙医保局",
          url: "https://example.test",
          status: "active",
          lastFetchedAt: "2026-09-11T00:00:00Z",
          lastChangeStatus: "unchanged",
          lastArtifactId: "artifact-1",
          lastArtifactSha256: "abc",
          fieldsToFill: ["P1", "C2"],
          alreadyFilled: ["P3"],
        },
      ],
    },
  ],
};

const submissions: ExtractionSubmissionRecord[] = [
  {
    id: "submission-1",
    cityId: "changsha",
    sourceId: "source-1",
    artifactId: "artifact-1",
    agentRunId: "run-001",
    agentVersion: "policy-ai-crawler@1",
    resultStatus: "partially_rejected",
    acceptedCount: 2,
    rejectedCount: 1,
    rejections: [{ fieldId: "C6", reason: "字段 C6 属官方无公开数据字段，禁止估算", quote: null }],
    payload: {
      accepted: [
        { fieldId: "P1", value: 66, unit: "元/小时", confidence: 0.95, quote: "单小时服务单价调整为 66 元", effectiveDate: null },
        { fieldId: "C2", value: "新一线", unit: null, confidence: 0.85, quote: "长沙为新一线城市", effectiveDate: null },
      ],
      notDisclosed: ["C6"],
    },
    submittedAt: "2026-09-11T00:00:00Z",
    createdAt: "2026-09-11T00:00:00Z",
    updatedAt: "2026-09-11T00:00:00Z",
  },
];

const candidates: SourceCandidate[] = [
  {
    id: "candidate-1",
    cityId: "changsha",
    name: "长沙市统计局统计公报",
    url: "https://tjj.changsha.gov.cn/tongji.html",
    domain: "tjj.changsha.gov.cn",
    title: "统计公报",
    publishedAt: null,
    summary: "常住人口与老龄化率数据。",
    targetFields: ["C3", "C4"],
    relevance: 0.9,
    origin: "ai_search",
    status: "candidate",
    promotedSourceId: null,
    reviewedBy: null,
    reviewedAt: null,
    note: null,
    createdAt: "2026-09-11T00:00:00Z",
    updatedAt: "2026-09-11T00:00:00Z",
  },
];

describe("PolicyCrawlStatusSection", () => {
  it("展示上一轮回传统计、待填字段与禁止估算字段", () => {
    render(<PolicyCrawlStatusSection targets={targets} submissions={submissions} loading={false} error={null} />);
    expect(screen.getByText("AI 抓取调度状态")).toBeTruthy();
    // 2 个来源字段待填（P1/C2 各一处），目录 3 个字段
    expect(screen.getByText("2 个 / 共 3 个自动爬虫字段")).toBeTruthy();
    expect(screen.getByText("C6")).toBeTruthy();
    expect(screen.getByText(/部分被拒 · 接收 2 \/ 拒绝 1/)).toBeTruthy();
    expect(screen.getByText(/上一轮被拒 1 条/)).toBeTruthy();
  });

  it("无记录时显示尚无记录并给出采用提示", () => {
    render(<PolicyCrawlStatusSection targets={targets} submissions={[]} loading={false} error={null} />);
    expect(screen.getByText("尚无记录")).toBeTruthy();
    expect(screen.getByText(/需在城市公式页逐条「采用」后才生效/)).toBeTruthy();
  });

  it("加载失败时展示错误并允许重试", () => {
    const onRetry = vi.fn();
    render(
      <PolicyCrawlStatusSection
        targets={undefined}
        submissions={[]}
        loading={false}
        error="网络不可达"
        onRetry={onRetry}
      />,
    );
    expect(screen.getByText("网络不可达")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe("PolicySourceCandidateSection", () => {
  it("展示待确认候选来源并可转为正式来源", async () => {
    const onPromote = vi.fn().mockResolvedValue(undefined);
    render(
      <PolicySourceCandidateSection
        candidates={candidates}
        loading={false}
        error={null}
        onPromote={onPromote}
        onReject={vi.fn()}
      />,
    );
    expect(screen.getByText("长沙市统计局统计公报")).toBeTruthy();
    expect(screen.getByText(/相关度 90%/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "转为来源" }));
    await waitFor(() => expect(onPromote).toHaveBeenCalledWith(candidates[0]));
  });

  it("没有候选来源时给出空态", () => {
    render(<PolicySourceCandidateSection candidates={[]} loading={false} error={null} />);
    expect(screen.getByText(/暂无待确认候选来源/)).toBeTruthy();
  });

  it("已处理候选来源折叠展示并标注状态", () => {
    render(
      <PolicySourceCandidateSection
        candidates={[{ ...candidates[0], id: "candidate-2", status: "rejected" }]}
        loading={false}
        error={null}
      />,
    );
    expect(screen.getByText("已处理 1 条")).toBeTruthy();
    expect(screen.getByText("已驳回")).toBeTruthy();
  });
});

describe("PolicyExtractionResultSection", () => {
  it("按字段列出建议值、置信度、原文引用与难度分档", () => {
    render(
      <PolicyExtractionResultSection
        submissions={submissions}
        catalog={targets.fieldCatalog}
        loading={false}
        error={null}
      />,
    );
    expect(screen.getByText("2 项建议值")).toBeTruthy();
    expect(screen.getByText("66")).toBeTruthy();
    expect(screen.getByText("元/小时")).toBeTruthy();
    expect(screen.getByText("95%")).toBeTruthy();
    expect(screen.getByText("“单小时服务单价调整为 66 元”")).toBeTruthy();
    expect(screen.getByText("新一线")).toBeTruthy();
    // B 档字段应显示归一化难度标签
    expect(screen.getByText("B · 需归一化")).toBeTruthy();
  });

  it("同字段多轮回传时只保留最新一条", () => {
    const older: ExtractionSubmissionRecord = {
      ...submissions[0],
      id: "submission-0",
      submittedAt: "2026-09-10T00:00:00Z",
      payload: {
        accepted: [
          { fieldId: "P1", value: 60, unit: "元/小时", confidence: 0.8, quote: "旧值", effectiveDate: null },
        ],
      },
    };
    render(
      <PolicyExtractionResultSection
        // 新的在前，旧的在后
        submissions={[submissions[0], older]}
        catalog={targets.fieldCatalog}
        loading={false}
        error={null}
      />,
    );
    expect(screen.getByText("66")).toBeTruthy();
    expect(screen.queryByText("60")).toBeNull();
  });

  it("无结果时给出空态并说明已运行轮数", () => {
    render(
      <PolicyExtractionResultSection
        submissions={[{ ...submissions[0], payload: { accepted: [] } }]}
        catalog={targets.fieldCatalog}
        loading={false}
        error={null}
      />,
    );
    expect(screen.getByText(/暂无 AI 抽取结果（已运行 1 轮）/)).toBeTruthy();
  });
});
