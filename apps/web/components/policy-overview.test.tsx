import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PolicyCityDetail } from "./policy-city-detail";
import { PolicyOverview } from "./policy-overview";
import { PolicyUploadPanel } from "./policy-upload-panel";
import type { PolicyCityDetailResponse, PolicyOverviewResponse } from "@/lib/policies";

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
      approvedFacts: [],
    },
  ],
  pendingReviewCount: 1,
  approvedFactCount: 3,
  alerts: [],
};

const detail: PolicyCityDetailResponse = {
  cityId: "changsha",
  cityName: "长沙",
  documents: [
    {
      id: "policy-1",
      cityId: "changsha",
      originalName: "长护险办法.docx",
      mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      size: 1024,
      sha256: "abc",
      source: "官方公告",
      storedPath: "policy_files/policy-1.docx",
      status: "review_pending",
      uploadedAt: "2026-09-08T00:00:00Z",
      updatedAt: "2026-09-08T00:00:00Z",
    },
  ],
  dataSources: [{ id: "source-1", cityId: "changsha", name: "官方公告", kind: "web", url: "https://example.test", status: "active", createdAt: "2026-09-08T00:00:00Z", updatedAt: "2026-09-08T00:00:00Z" }],
  facts: [{ id: "fact-1", documentId: "policy-1", cityId: "changsha", fieldId: "fundPaymentRatio", value: 0.85, unit: "比例", confidence: 0.92, source: "第4条", status: "candidate", reviewer: null, reviewedAt: null, effectiveDate: null, createdAt: "2026-09-08T00:00:00Z", updatedAt: "2026-09-08T00:00:00Z" }],
  approvedFacts: [],
  pendingReviewCount: 1,
  projects: [{ id: "project-1", name: "长沙项目" }],
};

afterEach(() => cleanup());

describe("policy center", () => {
  it("filters the global policy overview by city and shows review badges", () => {
    const onCityChange = vi.fn();
    render(<PolicyOverview initialData={overview} onCityChange={onCityChange} />);

    expect(screen.getByRole("heading", { name: "政策资料" })).toBeInTheDocument();
    expect(screen.getByText("待审核 1" )).toBeInTheDocument();
    expect(screen.getByText("已确认 3" )).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("城市"), { target: { value: "changsha" } });
    expect(onCityChange).toHaveBeenCalledWith("changsha");
  });

  it("renders empty policy guidance", () => {
    render(<PolicyOverview initialData={{ ...overview, cities: [], pendingReviewCount: 0, approvedFactCount: 0 }} />);
    expect(screen.getByText("暂无政策资料")).toBeInTheDocument();
  });

  it("keeps candidate review explicit and warns against overwriting project inputs", () => {
    const onReview = vi.fn();
    render(<PolicyCityDetail data={detail} onReview={onReview} />);

    expect(screen.getByText("待审核")).toBeInTheDocument();
    expect(screen.getByText("fundPaymentRatio")).toBeInTheDocument();
    expect(screen.getByText("政策候选值不会自动覆盖项目参数；请在城市项目页面人工确认参考值后再保存和重算。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "通过" }));
    expect(onReview).toHaveBeenCalledWith("policy-1", "fact-1", "approve");
  });

  it("submits explicit candidate JSON for local parsing before review", async () => {
    const onParse = vi.fn().mockResolvedValue(undefined);
    render(<PolicyCityDetail data={detail} onParse={onParse} />);

    fireEvent.change(screen.getByRole("textbox", { name: /候选字段 JSON/ }), { target: { value: '[{"fieldId":"P2","value":0.85}]' } });
    fireEvent.click(screen.getByRole("button", { name: "解析候选字段" }));

    await waitFor(() => expect(onParse).toHaveBeenCalledWith("policy-1", [{ fieldId: "P2", value: 0.85 }]));
  });

  it("accepts only local Word, Excel and PDF files", async () => {
    const onUpload = vi.fn().mockResolvedValue({ ...detail.documents[0], status: "uploaded" });
    render(<PolicyUploadPanel cityId="changsha" onUpload={onUpload} />);
    const input = screen.getByLabelText("上传政策文件");
    fireEvent.change(input, { target: { files: [new File(["policy"], "policy.pdf", { type: "application/pdf" })] } });
    await waitFor(() => expect(onUpload).toHaveBeenCalled());
    expect(onUpload).toHaveBeenCalledWith(expect.objectContaining({ name: "policy.pdf" }), "changsha");
  });
});
