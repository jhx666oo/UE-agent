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

export type PolicyFact = {
  id: string;
  cityId: string;
  documentId: string | null;
  fieldId: string | null;
  fieldName?: string | null;
  value?: number | string | null;
  quote?: string | null;
  source?: string | null;
  effectiveDate?: string | null;
  status: "candidate" | "approved" | "rejected";
  reviewer?: string | null;
  reviewedAt?: string | null;
  createdAt?: string;
  updatedAt?: string;
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

export type CityPolicyExtract = {
  cityId: string;
  cityName: string;
  hasData: boolean;
  documentCount: number;
  sourceCount: number;
  activeSourceCount: number;
  latestFetchedAt: string | null;
  latestUpdatedAt: string | null;
  pendingReviewCount: number;
  approvedFactCount: number;
  pendingFacts: PolicyFact[];
  approvedFacts: PolicyFact[];
  href: string;
};

const FACT_STATUS_LABELS: Record<PolicyFact["status"], string> = {
  candidate: "待审核",
  approved: "已采用",
  rejected: "已驳回",
};

export function factStatusLabel(status: string): string {
  return FACT_STATUS_LABELS[status as PolicyFact["status"]] ?? status;
}

/** 把单城市政策详情压成总览页「政策信息提炼区」需要的摘要。 */
export function buildCityPolicyExtract(detail: PolicyCityDetailResponse): CityPolicyExtract {
  const facts = (detail.facts as PolicyFact[]).filter((fact) => fact && typeof fact === "object");
  const activeSources = detail.dataSources.filter((source) => source.status === "active");
  const fetchedTimes = detail.dataSources
    .map((source) => source.lastFetchedAt)
    .filter((value): value is string => Boolean(value))
    .concat(detail.documents.map((document) => document.updatedAt).filter(Boolean));
  const updatedTimes = [
    ...detail.dataSources.map((source) => source.updatedAt),
    ...detail.documents.map((document) => document.updatedAt),
    ...facts.map((fact) => fact.updatedAt ?? fact.createdAt ?? ""),
  ].filter((value): value is string => Boolean(value));
  return {
    cityId: detail.cityId,
    cityName: detail.cityName,
    hasData: detail.dataSources.length > 0 || detail.documents.length > 0 || facts.length > 0,
    documentCount: detail.documents.length,
    sourceCount: detail.dataSources.length,
    activeSourceCount: activeSources.length,
    latestFetchedAt: fetchedTimes.length ? fetchedTimes.sort().at(-1)! : null,
    latestUpdatedAt: updatedTimes.length ? updatedTimes.sort().at(-1)! : null,
    pendingReviewCount: facts.filter((fact) => fact.status === "candidate").length,
    approvedFactCount: facts.filter((fact) => fact.status === "approved").length,
    pendingFacts: facts.filter((fact) => fact.status === "candidate"),
    approvedFacts: facts.filter((fact) => fact.status === "approved"),
    href: `/policies/${encodeURIComponent(detail.cityId)}`,
  };
}

export type DataSourceInput = {
  cityId: string;
  name: string;
  kind?: string;
  url: string;
  timeoutSeconds?: number | null;
  maxBytes?: number | null;
  note?: string | null;
};

/** 抽取难度分档，决定 WorkBuddy 的抽取预期与禁忌。 */
export type FieldDifficulty = "A" | "B" | "C" | "D";

export type FieldCatalogEntry = {
  id: string;
  name: string;
  unit: string | null;
  valueType: "number" | "string";
  options: string[] | null;
  block: string | null;
  difficulty: FieldDifficulty;
  neverEstimate: boolean;
};

export type CrawlTargetSource = {
  sourceId: string;
  name: string | null;
  url: string | null;
  status: DataSourceStatus;
  lastFetchedAt: string | null;
  lastChangeStatus: string | null;
  lastArtifactId: string | null;
  lastArtifactSha256: string | null;
  fieldsToFill: string[];
  alreadyFilled: string[];
};

export type CrawlTargetsResponse = {
  generatedAt: string;
  readScope: string;
  fieldCatalog: FieldCatalogEntry[];
  fieldFamilies: Array<{ family: string; queryTemplate: string; fields: string[]; sourceHint: string }>;
  difficultyLevels: Record<FieldDifficulty, string>;
  neverEstimateFields: string[];
  cities: Array<{ cityId: string; cityName: string; sources: CrawlTargetSource[] }>;
};

/** 候选来源状态：API 侧新建默认 "candidate"，人工处理后转 promoted / rejected。 */
export type SourceCandidateStatus = "candidate" | "promoted" | "rejected";

/** AI 检索发现的候选来源，需人工确认后才转为正式 DataSource。 */
export type SourceCandidate = {
  id: string;
  cityId: string;
  name: string | null;
  url: string;
  domain: string | null;
  title: string | null;
  publishedAt: string | null;
  summary: string | null;
  targetFields: string[];
  relevance: number | null;
  origin: string;
  status: SourceCandidateStatus;
  promotedSourceId: string | null;
  reviewedBy: string | null;
  reviewedAt: string | null;
  note: string | null;
  createdAt: string;
  updatedAt: string;
};

export type ExtractionSubmissionRecord = {
  id: string;
  cityId: string;
  sourceId: string | null;
  artifactId: string | null;
  agentRunId: string | null;
  agentVersion: string | null;
  resultStatus: "accepted" | "partially_rejected" | "rejected";
  acceptedCount: number;
  rejectedCount: number;
  rejections: Array<{ fieldId: string | null; reason: string; quote: string | null }>;
  payload?: {
    submissions?: unknown[];
    accepted?: Array<{
      fieldId: string;
      value: number | string;
      unit: string | null;
      confidence: number | null;
      quote: string | null;
      effectiveDate: string | null;
    }>;
    notDisclosed?: string[];
  };
  submittedAt: string;
  createdAt: string;
  updatedAt: string;
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

/** 派活清单：城市来源、增量待填字段、字段目录与检索提示。 */
export function getCrawlTargets() {
  return apiFetch<CrawlTargetsResponse>("/api/policies/crawl-targets");
}

export function listSourceCandidates(cityId?: string, status?: SourceCandidateStatus) {
  const params = new URLSearchParams();
  if (cityId) params.set("cityId", cityId);
  if (status) params.set("status", status);
  const query = params.toString();
  return apiFetch<SourceCandidate[]>(`/api/policies/source-candidates${query ? `?${query}` : ""}`);
}

/** 人工确认：候选来源转为正式 DataSource，纳入后续抓取。 */
export function promoteSourceCandidate(candidateId: string) {
  return apiFetch<SourceCandidate>(`/api/policies/source-candidates/${encodeURIComponent(candidateId)}/promote`, {
    method: "POST",
  });
}

export function rejectSourceCandidate(candidateId: string, reason?: string) {
  return apiFetch<SourceCandidate>(`/api/policies/source-candidates/${encodeURIComponent(candidateId)}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

/** 回传审计记录：页面「上次 AI 抓取新增了多少」的数据来源。 */
export function listExtractionSubmissions(cityId?: string, limit?: number) {
  const params = new URLSearchParams();
  if (cityId) params.set("cityId", cityId);
  if (limit) params.set("limit", String(limit));
  const query = params.toString();
  return apiFetch<ExtractionSubmissionRecord[]>(`/api/policies/extraction-submissions${query ? `?${query}` : ""}`);
}

const DIFFICULTY_LABELS: Record<FieldDifficulty, string> = {
  A: "A · 政策直读",
  B: "B · 需归一化",
  C: "C · 统计公报",
  D: "D · 无公开数据",
};

export function difficultyLabel(difficulty: string): string {
  return DIFFICULTY_LABELS[difficulty as FieldDifficulty] ?? difficulty;
}

const CANDIDATE_STATUS_LABELS: Record<SourceCandidateStatus, string> = {
  candidate: "待确认",
  promoted: "已转正",
  rejected: "已驳回",
};

export function candidateStatusLabel(status: string): string {
  return CANDIDATE_STATUS_LABELS[status as SourceCandidateStatus] ?? status;
}

const SUBMISSION_STATUS_LABELS: Record<ExtractionSubmissionRecord["resultStatus"], string> = {
  accepted: "全部接收",
  partially_rejected: "部分被拒",
  rejected: "全部被拒",
};

export function submissionStatusLabel(status: string): string {
  return SUBMISSION_STATUS_LABELS[status as ExtractionSubmissionRecord["resultStatus"]] ?? status;
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
