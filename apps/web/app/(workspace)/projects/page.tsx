"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { IconFolderPlus } from "@tabler/icons-react";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { listProjects, type ProjectRecord } from "@/lib/api";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((requestError) => setError(requestError instanceof Error ? requestError.message : "项目加载失败"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="PROJECTS"
        title="项目"
        description="每个测算项目都记录范围、假设、模型版本和复核状态。"
        actions={
          <Button asChild>
            <Link href="/projects/new">
              <IconFolderPlus size={16} stroke={1.8} />
              新建项目
            </Link>
          </Button>
        }
      />
      {loading ? (
        <div className="space-y-3" aria-label="正在加载项目">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : error ? (
        <Card className="border-danger/30">
          <CardContent className="p-5 text-sm text-danger">{error}</CardContent>
        </Card>
      ) : projects.length === 0 ? (
        <EmptyState title="还没有测算项目" description="创建第一个项目后，可以直接进入 U1 参数测算工作台。" actionLabel="创建项目" actionHref="/projects/new" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {projects.map((project) => (
            <Card key={project.id}>
              <CardHeader>
                <CardTitle>{project.name}</CardTitle>
                <p className="text-sm text-muted-foreground">{project.city}{project.district ? ` · ${project.district}` : ""}</p>
              </CardHeader>
              <CardContent className="flex items-center justify-between gap-4 pt-0">
                <div className="text-xs text-muted-foreground">{project.scenarios.length} 个场景 · 更新于 {new Date(project.updatedAt).toLocaleString("zh-CN")}</div>
                <Button asChild size="sm" variant="outline"><Link href={`/projects/${project.id}/u1`}>打开项目</Link></Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
