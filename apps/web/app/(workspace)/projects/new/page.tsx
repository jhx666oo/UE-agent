"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@ue-agent/ui/components/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@ue-agent/ui/components/card";
import { Input } from "@ue-agent/ui/components/input";
import { Label } from "@ue-agent/ui/components/label";
import { PageHeader } from "@/components/page-header";
import { createProject } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const [district, setDistrict] = useState("");
  const [baseMonth, setBaseMonth] = useState("");
  const [stationMode, setStationMode] = useState("自营");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || !city.trim()) {
      setError("请填写项目名称和目标城市");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const project = await createProject({
        name: name.trim(),
        city: city.trim(),
        district: district.trim() || null,
        baseMonth: baseMonth || null,
        stationMode,
      });
      router.push(`/projects/${project.id}/u1`);
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "项目保存失败，请稍后重试");
      setSaving(false);
    }
  }

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

      <form className="max-w-3xl" onSubmit={handleSubmit}>
        <Card>
        <CardHeader>
          <CardTitle>项目基本信息</CardTitle>
          <CardDescription>项目创建后会自动生成基准场景，并进入 U1 参数测算工作台。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="project-name">项目名称</Label>
            <Input id="project-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：湖南长护险 U1 城市选址" />
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="target-city">目标城市</Label>
              <Input id="target-city" value={city} onChange={(event) => setCity(event.target.value)} placeholder="输入城市名称" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="target-district">目标区县（可选）</Label>
              <Input id="target-district" value={district} onChange={(event) => setDistrict(event.target.value)} placeholder="例如：岳麓区" />
            </div>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="base-month">基准月份</Label>
              <Input id="base-month" type="month" value={baseMonth} onChange={(event) => setBaseMonth(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="station-mode">站点模式</Label>
              <select
                id="station-mode"
                value={stationMode}
                onChange={(event) => setStationMode(event.target.value)}
                className="flex h-10 w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-foreground shadow-sm outline-none focus:border-focus-ring focus:ring-2 focus:ring-focus-ring/20"
              >
                <option value="自营">自营</option>
                <option value="收购">收购</option>
                <option value="联营">联营</option>
              </select>
            </div>
          </div>
          {error ? <p className="rounded-md border border-danger/20 bg-danger-subtle px-3 py-2 text-sm text-danger">{error}</p> : null}
          <div className="flex items-center justify-end gap-3 border-t border-border pt-5">
            <Button asChild variant="outline">
              <Link href="/projects">取消</Link>
            </Button>
            <Button type="submit" disabled={saving}>{saving ? "保存中…" : "保存并继续"}</Button>
          </div>
        </CardContent>
        </Card>
      </form>
    </div>
  );
}
