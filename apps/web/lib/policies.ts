import { apiFetch, buildApiUrl } from "@/lib/api";

export type PolicyDocumentStatus = "uploaded" | "parsing" | "review_pending" | "approved" | "rejected";
export type DataSourceStatus = "active" | "paused" | "error";

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
  timeoutSeconds?: number | null;
  maxBytes?: number | null;
  note?: string | null;
  lastFetchedAt?: string | null;
  lastHttpStatus?: number | null;
  lastChangeStatus?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type CrawlArtifact = {
  artifactId: string;
  sourceId: string;
  cityId: string;
  requestedUrl: string;
  finalUrl: string | null;
  fetchedAt: string;
  httpStatus: number | null;
  contentType: string | null;
  contentLength: number | null;
  sha256: string | null;
  storedPath: string | null;
  title: string | null;
  changeStatus: "first_fetch" | "unchanged" | "new_version" | null;
  status: "success" | "failed";
  errorMessage: string | null;
  suggestions?: Array<{ fieldId: string; name: string; value: number | string; quote: string }>;
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
  facts: unknown[];
  approvedFacts: unknown[];
  pendingReviewCount: number;
  projects: Array<{ id: string; name: string }>;
};

export type DataSourceInput = {
  cityId: string;
  name: string;
  kind?: string;
  url: string;
  timeoutSeconds?: number | null;
  maxBytes?: number | null;
  note?: string | null;
};

export function getPolicyOverview(cityIds: string[] = []) {
  const query = cityIds.length ? `?cityIds=${encodeURIComponent(cityIds.join(","))}` : "";
  return apiFetch<PolicyOverviewResponse>(`/api/policies/overview${query}`);
}

export function getPolicyCityDetail(cityId: string) {
  return apiFetch<PolicyCityDetailResponse>(`/api/policies/cities/${encodeURIComponent(cityId)}`);
}

export function listPolicySources(cityId?: string) {
  const query = cityId ? `?cityId=${encodeURIComponent(cityId)}` : "";
  return apiFetch<DataSource[]>(`/api/policies/sources${query}`);
}

export function createPolicySource(input: DataSourceInput) {
  return apiFetch<DataSource>("/api/policies/sources", { method: "POST", body: JSON.stringify(input) });
}

export function updatePolicySource(
  sourceId: string,
  input: Partial<Pick<DataSource, "name" | "kind" | "url" | "status" | "timeoutSeconds" | "maxBytes" | "note">>,
) {
  return apiFetch<DataSource>(`/api/policies/sources/${encodeURIComponent(sourceId)}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function crawlPolicySource(sourceId: string) {
  return apiFetch<CrawlArtifact>(`/api/policies/sources/${encodeURIComponent(sourceId)}/crawl`, { method: "POST" });
}

export function listSourceArtifacts(sourceId: string) {
  return apiFetch<CrawlArtifact[]>(`/api/policies/sources/${encodeURIComponent(sourceId)}/artifacts`);
}

export function getCrawlArtifactUrl(artifactId: string) {
  return buildApiUrl(`/api/policies/artifacts/${encodeURIComponent(artifactId)}/content`);
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
