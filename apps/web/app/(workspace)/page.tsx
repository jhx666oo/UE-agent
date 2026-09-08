import Link from "next/link";
import { IconArrowRight, IconMap2, IconFolder, IconShieldCheck } from "@tabler/icons-react";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardHeader, CardTitle } from "@ue-agent/ui/components/card";

export default function WorkspaceHomePage() {
  return (
    <div className="space-y-8">
      <section className="max-w-3xl space-y-3">
        <p className="section-label">UE-AGENT / WORKSPACE</p>
        <h1 className="text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
          把长护险测算，变成一套可复核的决策流程。
        </h1>
        <p className="max-w-2xl text-base leading-7 text-muted-foreground">
          从项目范围、关键假设到数据准备和结果复核，每一个结论都保留来源、版本和人工确认痕迹。
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <Button asChild>
            <Link href="/projects">
              查看项目 <IconArrowRight size={16} stroke={1.8} />
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/u1">进入 U1 城市选址</Link>
          </Button>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <div className="mb-3 flex size-10 items-center justify-center rounded-md bg-primary-subtle text-primary">
              <IconFolder size={20} stroke={1.8} />
            </div>
            <CardTitle>项目化管理</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-6 text-muted-foreground">把测算范围、版本和复核状态收拢到一个项目里。</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="mb-3 flex size-10 items-center justify-center rounded-md bg-info-subtle text-info">
              <IconMap2 size={20} stroke={1.8} />
            </div>
            <CardTitle>城市选址</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-6 text-muted-foreground">为 U1 阶段保留参数、数据和结果的完整链路。</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="mb-3 flex size-10 items-center justify-center rounded-md bg-success-subtle text-success">
              <IconShieldCheck size={20} stroke={1.8} />
            </div>
            <CardTitle>可复核结论</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-6 text-muted-foreground">先明确口径，再允许计算，避免把假设误当成事实。</p>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
