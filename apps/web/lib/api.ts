export type FormulaStatus = "ok" | "formula_error" | "unavailable";

export type FormulaValue = {
  value: number | string | null;
  status: FormulaStatus;
  errorCode: string | null;
};

export type ParameterDefinition = {
  id: string;
  name: string;
  unit: string;
  excelCell: string;
  inputKind: "manual" | "reference_or_manual" | "formula";
  valueType: "number" | "string";
  stage: string;
  sourceType: string;
  required: boolean;
  parityStatus: "parity" | "needs_business_confirmation";
  block: string;
  blockOrder: number;
  options?: string[] | null;
};

export type FieldValueState = "empty" | "suggestion_ready" | "accepted" | "overridden" | "manual" | "formula";

export type FieldValueView = {
  fieldId: string;
  name: string;
  unit: string;
  sourceType: string;
  valueType?: string | null;
  block: string;
  blockOrder: number;
  readOnly: boolean;
  currentValue: number | string | null;
  suggestedValue: number | string | null;
  suggestedSource: {
    sourceName?: string;
    url?: string;
    artifactId?: string;
    quote?: string;
  } | null;
  suggestedAt: string | null;
  valueState: FieldValueState;
  options?: string[] | null;
};

export type ScenarioValuesResponse = {
  scenarioId: string;
  fields: FieldValueView[];
};

export type U1ModelSpec = {
  modelVersion: string;
  parameters: ParameterDefinition[];
  baselineInputs: Record<string, number | string | null>;
  issues: ModelIssue[];
};

export type ModelIssue = {
  code: string;
  excelCell: string;
  severity: string;
  status: string;
  message: string;
};

export type ProjectRecord = {
  id: string;
  name: string;
  cityId?: string | null;
  city: string;
  district: string | null;
  baseMonth: string | null;
  stationMode: string;
  createdAt: string;
  updatedAt: string;
  scenarios: ScenarioRecord[];
};

export type ScenarioRecord = {
  id: string;
  name: string;
  inputs: Record<string, number | string | null>;
  result: U1Result | null;
  status: "draft" | "stale" | "calculating" | "calculated" | "confirmed" | "failed" | "blocked";
  createdAt: string;
  updatedAt: string;
  inputSnapshot?: Record<string, number | string | null>;
  calculatedAt?: string | null;
  resultSnapshotId?: string | null;
};

export type CalculationSnapshot = {
  snapshotId: string;
  projectId: string;
  scenarioId: string;
  inputSnapshot: Record<string, number | string | null>;
  resultSnapshot: U1Result;
  modelVersion: string | null;
  calculatedAt: string;
  status: "calculated" | "confirmed" | "blocked" | "stale";
  issues: ModelIssue[];
};

export type U1Result = {
  modelVersion: string;
  status: "ok" | "blocked";
  parameters: Record<string, number | string | null>;
  months: MonthlyProjection[];
  stageSummary: Record<string, Record<string, number | FormulaValue>>;
  headlineMetrics: Record<string, FormulaValue>;
  issues: ModelIssue[];
};

export type MonthlyProjection = {
  month: number;
  stage: string;
  signedCustomers: FormulaValue;
  singleCustomerMonthRevenue: FormulaValue;
  longTermCareRevenue: FormulaValue;
  auxiliaryRevenue: FormulaValue;
  totalRevenue: FormulaValue;
  caregivers: FormulaValue;
  caregiverCost: FormulaValue;
  salesCost: FormulaValue;
  nurseCost: FormulaValue;
  variableCost: FormulaValue;
  fixedCost: FormulaValue;
  grossProfit: FormulaValue;
  netProfit: FormulaValue;
  grossMargin: FormulaValue;
  netMargin: FormulaValue;
  cumulativeNetProfit: FormulaValue;
  cumulativeCashFlow: FormulaValue;
  cashFlowPositiveMarker: FormulaValue;
  cashFlowPositiveMonth: FormulaValue;
  breakEvenCustomers: FormulaValue;
};

export class ApiError extends Error {
  readonly code: string;
  readonly payload: unknown;

  constructor(code: string, message: string, payload?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.payload = payload;
  }
}

export function buildApiUrl(path: string, baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000") {
  return `${baseUrl.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(buildApiUrl(path), { ...init, headers });
  const payload = (await response.json().catch(() => null)) as T | { error?: { code?: string; message?: string } } | null;
  if (!response.ok) {
    const error = payload && typeof payload === "object" && "error" in payload ? payload.error : null;
    if (payload && typeof payload === "object" && "issues" in payload && Array.isArray(payload.issues)) {
      const firstIssue = payload.issues.find((issue) => issue && typeof issue === "object" && "message" in issue) as { message?: string } | undefined;
      throw new ApiError("MODEL_BLOCKED", firstIssue?.message ?? "测算被必要输入阻断", payload);
    }
    throw new ApiError(error?.code ?? `HTTP_${response.status}`, error?.message ?? `请求失败（${response.status}）`, payload);
  }
  return payload as T;
}

export function formatFormulaValue(value: FormulaValue | null | undefined): string {
  if (!value || value.status === "unavailable") return "不可用";
  if (value.status === "formula_error") return `不可计算：${value.errorCode ?? "公式错误"}`;
  if (value.value === null) return "未计算";
  if (typeof value.value === "number") return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value.value);
  return value.value;
}

export function listProjects() {
  return apiFetch<ProjectRecord[]>("/api/projects");
}

export function getModelSpec() {
  return apiFetch<U1ModelSpec>("/api/model/u1");
}

export function createProject(input: Omit<ProjectRecord, "id" | "createdAt" | "updatedAt" | "scenarios">) {
  return apiFetch<ProjectRecord>("/api/projects", { method: "POST", body: JSON.stringify(input) });
}

export function getProject(projectId: string) {
  return apiFetch<ProjectRecord>(`/api/projects/${projectId}`);
}

export type DeleteProjectResponse = {
  deleted: boolean;
  projectId: string;
};

export function deleteProject(projectId: string) {
  return apiFetch<DeleteProjectResponse>(`/api/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
}

export function listScenarioSnapshotsForProject(projectId: string) {
  return apiFetch<CalculationSnapshot[]>(`/api/projects/${encodeURIComponent(projectId)}/snapshots`);
}

export function createScenario(projectId: string, input: { name: string; inputs?: Record<string, number | string | null> }) {
  return apiFetch<ScenarioRecord>(`/api/projects/${projectId}/scenarios`, { method: "POST", body: JSON.stringify(input) });
}

export function updateScenario(projectId: string, scenarioId: string, input: { inputs: Record<string, number | string | null> }) {
  return apiFetch<ScenarioRecord>(`/api/projects/${projectId}/scenarios/${scenarioId}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

export function listScenarioSnapshots(projectId: string, scenarioId: string) {
  return apiFetch<CalculationSnapshot[]>(`/api/projects/${projectId}/scenarios/${scenarioId}/snapshots`);
}

export function confirmScenario(projectId: string, scenarioId: string) {
  return apiFetch<ScenarioRecord>(`/api/projects/${projectId}/scenarios/${scenarioId}/confirm`, { method: "POST" });
}

export function calculateScenario(projectId: string, scenarioId: string) {
  return apiFetch<U1Result>(`/api/projects/${projectId}/scenarios/${scenarioId}/calculate`, { method: "POST" });
}

export function listScenarioValues(projectId: string, scenarioId: string) {
  return apiFetch<ScenarioValuesResponse>(`/api/projects/${projectId}/scenarios/${scenarioId}/values`);
}

export function patchScenarioValue(projectId: string, scenarioId: string, fieldId: string, value: number | string | null) {
  return apiFetch<FieldValueView>(`/api/projects/${projectId}/scenarios/${scenarioId}/values/${encodeURIComponent(fieldId)}`, {
    method: "PATCH",
    body: JSON.stringify({ value }),
  });
}

export function acceptFieldSuggestion(projectId: string, scenarioId: string, fieldId: string) {
  return apiFetch<FieldValueView>(`/api/projects/${projectId}/scenarios/${scenarioId}/values/${encodeURIComponent(fieldId)}/accept-suggestion`, {
    method: "POST",
  });
}
