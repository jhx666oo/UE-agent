import Link from "next/link";
import { IconArrowRight, IconCheck, IconDatabase, IconMapPin } from "@tabler/icons-react";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Separator } from "@ue-agent/ui/components/separator";
import { EmptyState } from "@/components/empty-state";
import { MetricCard } from "@/components/metric-card";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { getU1StepLabel, U1_STEPS } from "@/lib/u1";

export default function U1Page() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="U1 / CITY SELECTION"
        title="U1 城市选址"
        description="先把口径和数据准备完整，再执行城市层面的 UE 测算和结果复核。"
        actions={
          <Button asChild>
            <Link href="/projects/new">
              开始一个项目 <IconArrowRight size={16} stroke={1.8} />
            </Link>
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>测算工作流</CardTitle>
          <CardDescription>每一步都要有可说明的输入和可追溯的确认记录。</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-5">
            {U1_STEPS.map((step, index) => (
              <div key={step} className="relative flex items-start gap-3 rounded-md border border-border bg-surface-subtle p-3 md:block md:min-h-24">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-surface-selected text-xs font-semibold text-primary">
                  {index + 1}
                </div>
                <div className="space-y-1 md:mt-3">
                  <p className="text-sm font-medium">{getU1StepLabel(step)}</p>
                  <StatusBadge status="未开始" />
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <section className="grid gap-4 md:grid-cols-3">
        <MetricCard label="已纳入城市" note="连接城市数据后展示" />
        <MetricCard label="可用数据集" note="等待数据源配置" />
        <MetricCard label="当前版本" note="项目创建后生成" />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-md bg-primary-subtle text-primary">
                <IconMapPin size={18} stroke={1.8} />
              </div>
              <div>
                <CardTitle>测算范围</CardTitle>
                <CardDescription>城市、时间和业务边界</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between gap-4 text-sm">
              <span className="text-muted-foreground">目标区域</span>
              <span className="font-medium">—</span>
            </div>
            <Separator />
            <div className="flex items-center justify-between gap-4 text-sm">
              <span className="text-muted-foreground">测算周期</span>
              <span className="font-medium">—</span>
            </div>
            <Separator />
            <div className="flex items-center justify-between gap-4 text-sm">
              <span className="text-muted-foreground">服务模式</span>
              <span className="font-medium">—</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-md bg-info-subtle text-info">
                <IconDatabase size={18} stroke={1.8} />
              </div>
              <div>
                <CardTitle>数据准备</CardTitle>
                <CardDescription>只展示已确认的数据状态</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <EmptyState title="尚未配置数据源" description="接入业务数据或上传经过确认的参数文件后，系统会在这里展示数据覆盖与质量检查结果。" />
          </CardContent>
        </Card>
      </section>

      <Card className="border-primary/20 bg-surface-selected/45">
        <CardContent className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <IconCheck className="mt-0.5 shrink-0 text-primary" size={18} stroke={2} />
            <div>
              <p className="text-sm font-medium">先完成口径确认，再进入计算</p>
              <p className="mt-1 text-sm text-muted-foreground">在计算服务接入前，系统不会生成城市排名、收益结论或默认建议。</p>
            </div>
          </div>
          <Button asChild variant="outline" className="shrink-0">
            <Link href="/projects/new">创建测算项目</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
