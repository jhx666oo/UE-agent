import { apiFetch, buildApiUrl } from "@/lib/api";

export type PolicyDocumentStatus = "uploaded" | "parsing" | "review_pending" | "approved" | "rejected";
export type PolicyFactStatus = "candidate" | "approved" | "rejected";
export type DataSourceStatus = "active" | "paused" | "error";

export type PolicyFact = {
  id: string;
  documentId: string;
  cityId: string;
  fieldId: string;
  value: unknown;
  unit: string | null;
  confidence: number | null;
  source: string | null;
  status: PolicyFactStatus;
  reviewer: string | null;
  reviewedAt: string | null;
  effectiveDate: string | null;
  createdAt: string;
  updatedAt: string;
};

export type PolicyDocument = {
  id: string;
  cityId: string;
  originalName: string;
  mimeType: string;
  size: number;
  sha256: string;
  source: string;
  storedPath: string;
  status: PolicyDocumentStatus;
  uploadedAt: string;
  updatedAt: string;
  factIds?: string[];
  pendingFactCount?: number;
};

export type DataSource = {
  id: string;
  cityId: string;
  name: string;
  kind: string;
  url: string | null;
  status: DataSourceStatus;
  createdAt: string;
  updatedAt: string;
};

export type PolicyCitySummary = {
  cityId: string;
  cityName: string;
  documentCount: number;
  latestUpdatedAt: string | null;
  pendingReviewCount: number;
  approvedFactCount: number;
  completeness: number | null;
  sourceStatus: DataSourceStatus | "missing";
  affectedProjectCount: number;
  approvedFacts: PolicyFact[];
};

export type PolicyAlert = {
  type: "policy";
  severity: "info" | "warning" | "danger";
  cityId: string;
  cityName: string;
  message: string;
  href: string;
};

export type PolicyOverviewResponse = {
  cities: PolicyCitySummary[];
  pendingReviewCount: number;
  approvedFactCount: number;
  alerts: PolicyAlert[];
};

export type PolicyCityDetailResponse = {
  cityId: string;
  cityName: string;
  documents: PolicyDocument[];
  dataSources: DataSource[];
  facts: PolicyFact[];
  approvedFacts: PolicyFact[];
  pendingReviewCount: number;
  projects: Array<{ id: string; name: string }>;
};

export type PolicyCandidateInput = {
  fieldId: string;
  value: unknown;
  unit?: string | null;
  confidence?: number | null;
  source?: string | null;
};

export function getPolicyOverview(cityIds: string[] = []) {
  const query = cityIds.length ? `?cityIds=${encodeURIComponent(cityIds.join(","))}` : "";
  return apiFetch<PolicyOverviewResponse>(`/api/policies/overview${query}`);
}

export function getPolicyCityDetail(cityId: string) {
  return apiFetch<PolicyCityDetailResponse>(`/api/policies/cities/${encodeURIComponent(cityId)}`);
}

export function uploadPolicyDocument(file: File, cityId: string, source = "本地上传") {
  const body = new FormData();
  body.append("cityId", cityId);
  body.append("source", source);
  body.append("file", file);
  return apiFetch<PolicyDocument>("/api/policies/documents/upload", { method: "POST", body });
}

export function getPolicyDocumentContentUrl(documentId: string) {
  return buildApiUrl(`/api/policies/documents/${encodeURIComponent(documentId)}/content`);
}

export function parsePolicyDocument(documentId: string, candidates: PolicyCandidateInput[] = []) {
  return apiFetch<PolicyDocument>(`/api/policies/documents/${documentId}/parse`, {
    method: "POST",
    body: JSON.stringify({ candidates }),
  });
}

export function reviewPolicyFact(
  documentId: string,
  factId: string,
  decision: "approve" | "reject",
  reviewer: string,
  options: { source?: string; effectiveDate?: string } = {},
) {
  return apiFetch<PolicyFact>(`/api/policies/documents/${documentId}/facts/${factId}/review`, {
    method: "POST",
    body: JSON.stringify({ decision, reviewer, ...options }),
  });
}

export function formatPolicyDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN");
}

export function formatPolicyValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未填写";
  if (typeof value === "number") return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 }).format(value);
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}
