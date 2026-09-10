"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { IconTrash } from "@tabler/icons-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@ue-agent/ui/components/alert-dialog";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent } from "@ue-agent/ui/components/card";
import { Skeleton } from "@ue-agent/ui/components/skeleton";
import { PageHeader } from "@/components/page-header";
import { CityProjectWorkbench } from "@/components/city-project-workbench";
import {
  createScenario,
  deleteProject,
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
  const router = useRouter();
  const projectId = params.projectId;
  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [spec, setSpec] = useState<U1ModelSpec | null>(null);
  const [scenario, setScenario] = useState<ScenarioRecord | null>(null);
  const [snapshots, setSnapshots] = useState<CalculationSnapshot[]>([]);
  const [values, setValues] = useState<ScenarioValuesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

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

  async function handleConfirmDelete() {
    if (!project) return;
    setDeleting(true);
    try {
      await deleteProject(project.id);
      toast.success(`已删除「${project.name}」`, { description: "测算场景与快照已一并清理，政策资料保留。" });
      router.push("/projects");
    } catch (deleteError) {
      const message = deleteError instanceof Error ? deleteError.message : "删除失败，请稍后重试";
      toast.error("删除失败", { description: message });
      setDeleting(false);
      setConfirmOpen(false);
    }
  }

  const backAction = (
    <Button asChild variant="ghost">
      <Link href="/projects">返回城市列表</Link>
    </Button>
  );

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="CITY / ERROR" title="城市测算加载失败" description={error} actions={backAction} />
        <Card className="border-danger/30"><CardContent className="p-5 text-sm text-danger">请确认 API 服务已启动，并检查城市编号是否有效。</CardContent></Card>
      </div>
    );
  }

  if (!project || !spec || !scenario || !values) {
    return <div className="space-y-5" aria-label="正在加载城市测算"><Skeleton className="h-20 w-full" /><Skeleton className="h-[520px] w-full" /></div>;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="CITY CALCULATION"
        title={project.name}
        description={`${project.city}${project.district ? ` · ${project.district}` : ""} · ${scenario.name}`}
        actions={
          <>
            <Button
              type="button"
              variant="ghost"
              className="text-danger hover:bg-danger/10 hover:text-danger"
              onClick={() => setConfirmOpen(true)}
              aria-label={`删除 ${project.name}`}
            >
              <IconTrash size={16} stroke={1.8} />
              删除城市
            </Button>
            {backAction}
          </>
        }
      />
      <CityProjectWorkbench project={project} scenario={scenario} spec={spec} initialSnapshots={snapshots} initialValues={values} />

      <AlertDialog
        open={confirmOpen}
        onOpenChange={(open) => {
          if (!open && !deleting) setConfirmOpen(false);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除「{project.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              删除后无法恢复。该城市测算对象及其关联数据将被永久移除，此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <ul className="space-y-1.5 rounded-md border border-border bg-surface-subtle p-3 text-sm">
            <li className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">城市</span>
              <span className="font-medium">{project.city}{project.district ? ` · ${project.district}` : ""}</span>
            </li>
            <li className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">测算场景</span>
              <span className="font-medium tabular-nums">{project.scenarios.length} 个</span>
            </li>
            <li className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">当前场景历史快照</span>
              <span className="font-medium tabular-nums">{snapshots.length} 条</span>
            </li>
            <li className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">计算快照与字段值历史</span>
              <span className="font-medium">一并删除</span>
            </li>
            <li className="flex items-center justify-between gap-4">
              <span className="text-muted-foreground">政策来源与抓取记录</span>
              <span className="font-medium text-success">保留</span>
            </li>
          </ul>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                void handleConfirmDelete();
              }}
              disabled={deleting}
            >
              {deleting ? "删除中…" : "确认删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
