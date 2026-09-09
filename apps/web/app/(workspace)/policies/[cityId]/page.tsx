"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { PageHeader } from "@/components/page-header";
import { PolicyCityDetail } from "@/components/policy-city-detail";
import { PolicyUploadPanel } from "@/components/policy-upload-panel";
import { getPolicyCityDetail, parsePolicyDocument, reviewPolicyFact, uploadPolicyDocument, type PolicyCandidateInput, type PolicyCityDetailResponse } from "@/lib/policies";

export default function PolicyCityPage() {
  const params = useParams<{ cityId: string }>();
  const cityId = decodeURIComponent(params.cityId);
  const [data, setData] = useState<PolicyCityDetailResponse | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setData(await getPolicyCityDetail(cityId));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "政策资料加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    getPolicyCityDetail(cityId)
      .then((nextData) => { if (active) setData(nextData); })
      .catch((requestError) => { if (active) setError(requestError instanceof Error ? requestError.message : "政策资料加载失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [cityId]);

  async function handleUpload(file: File, selectedCityId: string) {
    const uploaded = await uploadPolicyDocument(file, selectedCityId);
    await load();
    return uploaded;
  }

  async function handleReview(documentId: string, factId: string, decision: "approve" | "reject") {
    await reviewPolicyFact(documentId, factId, decision, "当前审核人");
    await load();
  }

  async function handleParse(documentId: string, candidates: PolicyCandidateInput[]) {
    await parsePolicyDocument(documentId, candidates);
    await load();
  }

  if (loading && !data) return <div className="space-y-4" aria-label="正在加载城市政策资料"><Skeleton className="h-24 w-full" /><Skeleton className="h-48 w-full" /><Skeleton className="h-48 w-full" /></div>;
  if (error && !data) return <div className="space-y-5"><PageHeader eyebrow="POLICY / CITY" title="城市政策资料加载失败" description={error} /><Card className="border-danger/30"><CardContent className="flex items-center justify-between gap-4 p-5"><p className="text-sm text-danger">请确认 API 服务已启动。</p><Button variant="outline" onClick={() => void load()}>重试</Button></CardContent></Card></div>;
  if (!data) return null;
  return <div className="space-y-6"><PolicyUploadPanel cityId={cityId} onUpload={handleUpload} /><PolicyCityDetail data={data} onParse={handleParse} onReview={handleReview} /></div>;
}
