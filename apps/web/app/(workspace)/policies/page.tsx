"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@ue-agent/ui/components/card";
import { Button } from "@ue-agent/ui/components/button";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { PageHeader } from "@/components/page-header";
import { PolicyOverview } from "@/components/policy-overview";
import { getPolicyOverview, type PolicyOverviewResponse } from "@/lib/policies";

export default function PoliciesPage() {
  const [data, setData] = useState<PolicyOverviewResponse | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load(cityIds: string[] = []): Promise<PolicyOverviewResponse> {
    setLoading(true);
    setError(null);
    return getPolicyOverview(cityIds)
      .then((nextData) => {
        setData(nextData);
        return nextData;
      })
      .catch((requestError) => {
        setError(requestError instanceof Error ? requestError.message : "政策资料加载失败");
        throw requestError;
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    let active = true;
    getPolicyOverview()
      .then((nextData) => { if (active) setData(nextData); })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "政策资料加载失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  if (loading && !data) return <div className="space-y-4" aria-label="正在加载政策资料"><Skeleton className="h-24 w-full" /><Skeleton className="h-56 w-full" /></div>;
  if (error && !data) return <div className="space-y-5"><PageHeader eyebrow="POLICY" title="政策资料加载失败" description={error} /><Card className="border-danger/30"><CardContent className="flex items-center justify-between gap-4 p-5"><p className="text-sm text-danger">请确认 API 服务已启动。</p><Button variant="outline" onClick={() => void load().catch(() => undefined)}>重试</Button></CardContent></Card></div>;
  return <PolicyOverview initialData={data} loadData={load} />;
}
