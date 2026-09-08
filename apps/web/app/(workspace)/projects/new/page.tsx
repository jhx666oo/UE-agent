import Link from "next/link";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Input } from "@ue-agent/ui/components/input";
import { Label } from "@ue-agent/ui/components/label";
import { PageHeader } from "@/components/page-header";

export default function NewProjectPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="NEW PROJECT"
        title="新建项目"
        description="先确定项目身份和测算基准，后续步骤会沿用这组信息。"
        actions={
          <Button asChild variant="ghost">
            <Link href="/projects">返回项目</Link>
          </Button>
        }
      />

      <Card className="max-w-3xl">
        <CardHeader>
          <CardTitle>项目基本信息</CardTitle>
          <CardDescription>当前阶段仅建立表单结构，保存能力将在接入项目服务后启用。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="project-name">项目名称</Label>
            <Input id="project-name" placeholder="例如：湖南长护险 U1 城市选址" />
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="target-city">目标城市</Label>
              <Input id="target-city" placeholder="输入城市名称" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="base-month">基准月份</Label>
              <Input id="base-month" type="month" />
            </div>
          </div>
          <div className="flex items-center justify-end gap-3 border-t border-border pt-5">
            <Button asChild variant="outline">
              <Link href="/projects">取消</Link>
            </Button>
            <Button disabled>保存并继续</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
