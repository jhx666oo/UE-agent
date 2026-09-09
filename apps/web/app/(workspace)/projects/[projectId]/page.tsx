"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { PageHeader } from "@/components/page-header";
import { CityProjectWorkbench } from "@/components/city-project-workbench";
import {
  createScenario,
  getModelSpec,
  getProject,
  listScenarioSnapshots,
  listScenarioValues,
  type CalculationSnapshot,
  type ProjectRecord,
  type ScenarioRecord,
  type ScenarioValuesResponse,
  type U1ModelSpec,
} from "@/lib/api";

export default function CityProjectPage() {
  const params = useParams<{ projectId: string }>();
  const projectId = params.projectId;
  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [spec, setSpec] = useState<U1ModelSpec | null>(null);
  const [scenario, setScenario] = useState<ScenarioRecord | null>(null);
  const [snapshots, setSnapshots] = useState<CalculationSnapshot[]>([]);
  const [values, setValues] = useState<ScenarioValuesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([getProject(projectId), getModelSpec()])
      .then(async ([nextProject, nextSpec]) => {
        const nextScenario = nextProject.scenarios[0] ?? (await createScenario(projectId, { name: "基准" }));
        const [nextSnapshots, nextValues] = await Promise.all([
          listScenarioSnapshots(projectId, nextScenario.id),
          listScenarioValues(projectId, nextScenario.id),
        ]);
        setProject(nextProject);
        setSpec(nextSpec);
        setScenario(nextScenario);
        setSnapshots(nextSnapshots);
        setValues(nextValues);
      })
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "城市测算加载失败"));
  }, [projectId]);

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="CITY / ERROR" title="城市测算加载失败" description={error} actions={<Button asChild variant="ghost"><Link href="/projects">返回城市列表</Link></Button>} />
        <Card className="border-danger/30"><CardContent className="p-5 text-sm text-danger">请确认 API 服务已启动，并检查城市编号是否有效。</CardContent></Card>
      </div>
    );
  }

  if (!project || !spec || !scenario || !values) {
    return <div className="space-y-5" aria-label="正在加载城市测算"><Skeleton className="h-20 w-full" /><Skeleton className="h-[520px] w-full" /></div>;
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="CITY CALCULATION" title={project.name} description={`${project.city}${project.district ? ` · ${project.district}` : ""} · ${scenario.name}`} actions={<Button asChild variant="ghost"><Link href="/projects">返回城市列表</Link></Button>} />
      <CityProjectWorkbench project={project} scenario={scenario} spec={spec} initialSnapshots={snapshots} initialValues={values} />
    </div>
  );
}
