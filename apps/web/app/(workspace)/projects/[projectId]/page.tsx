"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { PageHeader } from "@/components/page-header";
import { CityProjectWorkbench } from "@/components/city-project-workbench";
import { createScenario, getModelSpec, getProject, listScenarioSnapshots, type CalculationSnapshot, type ProjectRecord, type ScenarioRecord, type U1ModelSpec } from "@/lib/api";

export default function CityProjectPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId;
  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [spec, setSpec] = useState<U1ModelSpec | null>(null);
  const [scenario, setScenario] = useState<ScenarioRecord | null>(null);
  const [snapshots, setSnapshots] = useState<CalculationSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([getProject(projectId), getModelSpec()])
      .then(async ([nextProject, nextSpec]) => {
        const nextScenario = nextProject.scenarios[0] ?? (await createScenario(projectId, { name: "基准" }));
        const nextSnapshots = await listScenarioSnapshots(projectId, nextScenario.id);
        setProject(nextProject);
        setSpec(nextSpec);
        setScenario(nextScenario);
        setSnapshots(nextSnapshots);
      })
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "项目加载失败"));
  }, [projectId]);

  if (error) {
    return <div className="space-y-6"><PageHeader eyebrow="CITY PROJECT / ERROR" title="项目加载失败" description={error} actions={<Button asChild variant="ghost"><Link href="/projects">返回城市项目</Link></Button>} /><Card className="border-danger/30"><CardContent className="p-5 text-sm text-danger">请确认 API 服务已启动，并检查项目编号是否有效。</CardContent></Card></div>;
  }

  if (!project || !spec || !scenario) {
    return <div className="space-y-5" aria-label="正在加载城市项目"><Skeleton className="h-20 w-full" /><Skeleton className="h-[520px] w-full" /></div>;
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="CITY PROJECT" title={project.name} description={`${project.city}${project.district ? ` · ${project.district}` : ""} · ${scenario.name}`} actions={<Button asChild variant="ghost"><Link href="/projects">返回城市项目</Link></Button>} />
      <CityProjectWorkbench project={project} scenario={scenario} spec={spec} initialSnapshots={snapshots} />
    </div>
  );
}
