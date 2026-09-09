"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { PageHeader } from "@/components/page-header";
import { PolicyCityDetail } from "@/components/policy-city-detail";
import {
  createPolicySource,
  crawlPolicySource,
  getPolicyCityDetail,
  listPolicySources,
  listSourceArtifacts,
  updatePolicySource,
  type CrawlArtifact,
  type DataSource,
  type PolicyCityDetailResponse,
} from "@/lib/policies";

export default function PolicyCityPage() {
  const params = useParams<{ cityId: string }>();
  const cityId = decodeURIComponent(params.cityId);
  const [data, setData] = useState<PolicyCityDetailResponse | undefined>();
  const [sources, setSources] = useState<DataSource[]>([]);
  const [artifacts, setArtifacts] = useState<CrawlArtifact[]>([]);
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
    <PolicyCityDetail
      data={data}
      sources={sources}
      artifacts={artifacts}
      onCreateSource={handleCreateSource}
      onToggleSource={handleToggleSource}
      onCrawl={handleCrawl}
    />
  );
}
