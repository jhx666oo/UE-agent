"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { PageHeader } from "@/components/page-header";
import { PolicyCityDetail } from "@/components/policy-city-detail";
import {
  PolicyCrawlStatusSection,
  PolicyExtractionResultSection,
  PolicySourceCandidateSection,
} from "@/components/policy-ai-crawl-sections";
import {
  createPolicySource,
  crawlPolicySource,
  getCrawlTargets,
  getPolicyCityDetail,
  listExtractionSubmissions,
  listPolicySources,
  listSourceArtifacts,
  listSourceCandidates,
  promoteSourceCandidate,
  rejectSourceCandidate,
  updatePolicySource,
  type CrawlArtifact,
  type CrawlTargetsResponse,
  type DataSource,
  type ExtractionSubmissionRecord,
  type PolicyCityDetailResponse,
  type SourceCandidate,
} from "@/lib/policies";

export default function PolicyCityPage() {
  const params = useParams<{ cityId: string }>();
  const cityId = decodeURIComponent(params.cityId);
  const [data, setData] = useState<PolicyCityDetailResponse | undefined>();
  const [sources, setSources] = useState<DataSource[]>([]);
  const [artifacts, setArtifacts] = useState<CrawlArtifact[]>([]);
  const [targets, setTargets] = useState<CrawlTargetsResponse | undefined>();
  const [candidates, setCandidates] = useState<SourceCandidate[]>([]);
  const [submissions, setSubmissions] = useState<ExtractionSubmissionRecord[]>([]);
  const [aiLoading, setAiLoading] = useState(true);
  const [aiError, setAiError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [detail, nextSources] = await Promise.all([
      getPolicyCityDetail(cityId),
      listPolicySources(cityId),
    ]);
    setData(detail);
    setSources(nextSources);
    const artifactLists = await Promise.all(nextSources.map((source) => listSourceArtifacts(source.id)));
    setArtifacts(artifactLists.flat());
  }, [cityId]);

  /** AI 抓取相关的三个区块单独加载：任一失败不应拖垮整页。供按钮触发。 */
  const loadAiSections = useCallback(async () => {
    const [targetsResult, candidatesResult, submissionsResult] = await Promise.allSettled([
      getCrawlTargets(),
      listSourceCandidates(cityId),
      listExtractionSubmissions(cityId, 10),
    ]);
    if (targetsResult.status === "fulfilled") setTargets(targetsResult.value);
    if (candidatesResult.status === "fulfilled") setCandidates(candidatesResult.value);
    if (submissionsResult.status === "fulfilled") setSubmissions(submissionsResult.value);
    const failure = [targetsResult, candidatesResult, submissionsResult].find(
      (item) => item.status === "rejected",
    );
    setAiError(
      failure?.status === "rejected"
        ? failure.reason instanceof Error
          ? failure.reason.message
          : "AI 抓取信息加载失败"
        : null,
    );
    setAiLoading(false);
  }, [cityId]);

  useEffect(() => {
    let active = true;
    Promise.all([getPolicyCityDetail(cityId), listPolicySources(cityId)])
      .then(async ([detail, nextSources]) => {
        const artifactLists = await Promise.all(nextSources.map((source) => listSourceArtifacts(source.id)));
        if (!active) return;
        setData(detail);
        setSources(nextSources);
        setArtifacts(artifactLists.flat());
      })
      .catch((requestError) => {
        if (active) setError(requestError instanceof Error ? requestError.message : "政策资料加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [cityId]);

  useEffect(() => {
    let active = true;
    Promise.allSettled([getCrawlTargets(), listSourceCandidates(cityId), listExtractionSubmissions(cityId, 10)])
      .then(([targetsResult, candidatesResult, submissionsResult]) => {
        if (!active) return;
        if (targetsResult.status === "fulfilled") setTargets(targetsResult.value);
        if (candidatesResult.status === "fulfilled") setCandidates(candidatesResult.value);
        if (submissionsResult.status === "fulfilled") setSubmissions(submissionsResult.value);
        const failure = [targetsResult, candidatesResult, submissionsResult].find(
          (item) => item.status === "rejected",
        );
        setAiError(
          failure?.status === "rejected"
            ? failure.reason instanceof Error
              ? failure.reason.message
              : "AI 抓取信息加载失败"
            : null,
        );
      })
      .finally(() => {
        if (active) setAiLoading(false);
      });
    return () => {
      active = false;
    };
  }, [cityId]);

  /** 供按钮触发的重载：显式置回加载态。 */
  const reloadAiSections = useCallback(async () => {
    setAiLoading(true);
    await loadAiSections();
  }, [loadAiSections]);

  async function handleCreateSource(input: { name: string; url: string }) {
    await createPolicySource({ cityId, name: input.name, url: input.url });
    await load();
  }

  async function handleToggleSource(source: DataSource) {
    await updatePolicySource(source.id, { status: source.status === "paused" ? "active" : "paused" });
    await load();
  }

  async function handleCrawl(source: DataSource) {
    await crawlPolicySource(source.id);
    await load();
    await loadAiSections();
  }

  async function handlePromoteCandidate(candidate: SourceCandidate) {
    await promoteSourceCandidate(candidate.id);
    await Promise.all([load(), loadAiSections()]);
  }

  async function handleRejectCandidate(candidate: SourceCandidate) {
    await rejectSourceCandidate(candidate.id, "人工驳回");
    await loadAiSections();
  }

  if (loading && !data) {
    return (
      <div className="space-y-4" aria-label="正在加载城市政策资料">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }
  if (error && !data) {
    return (
      <div className="space-y-5">
        <PageHeader eyebrow="POLICY / CITY" title="城市政策资料加载失败" description={error} />
        <Card className="border-danger/30">
          <CardContent className="flex items-center justify-between gap-4 p-5">
            <p className="text-sm text-danger">请确认 API 服务已启动。</p>
            <Button variant="outline" onClick={() => void load()}>重试</Button>
          </CardContent>
        </Card>
      </div>
    );
  }
  if (!data) return null;
  return (
    <div className="space-y-5">
      <PolicyCrawlStatusSection
        targets={targets}
        submissions={submissions}
        loading={aiLoading}
        error={aiError}
        onRetry={() => void reloadAiSections()}
      />
      <PolicyCityDetail
        data={data}
        sources={sources}
        artifacts={artifacts}
        onCreateSource={handleCreateSource}
        onToggleSource={handleToggleSource}
        onCrawl={handleCrawl}
      />
      <PolicySourceCandidateSection
        candidates={candidates}
        loading={aiLoading}
        error={aiError}
        onPromote={handlePromoteCandidate}
        onReject={handleRejectCandidate}
        onRetry={() => void reloadAiSections()}
      />
      <PolicyExtractionResultSection
        submissions={submissions}
        catalog={targets?.fieldCatalog ?? []}
        loading={aiLoading}
        error={aiError}
        onRetry={() => void reloadAiSections()}
      />
    </div>
  );
}
