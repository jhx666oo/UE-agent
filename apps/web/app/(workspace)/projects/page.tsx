import Link from "next/link";
import { IconFolderPlus } from "@tabler/icons-react";
import { Button } from "@ue-agent/ui/components/button";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";

export default function ProjectsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="PROJECTS"
        title="项目"
        description="每个测算项目都记录范围、假设、数据版本和复核状态，后续再接入真实持久化数据。"
        actions={
          <Button asChild>
            <Link href="/projects/new">
              <IconFolderPlus size={16} stroke={1.8} />
              新建项目
            </Link>
          </Button>
        }
      />
      <EmptyState
        title="还没有连接项目数据"
        description="第一阶段先完成项目入口和信息结构，连接后端数据库后，这里会展示可继续编辑和复核的测算项目。"
        actionLabel="创建项目草稿"
        actionHref="/projects/new"
      />
    </div>
  );
}
