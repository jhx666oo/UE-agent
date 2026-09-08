"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { IconChevronRight, IconPlus } from "@tabler/icons-react";
import { Button } from "@ue-agent/ui/components/button";
import { navigationItems } from "@/components/sidebar";
import { isNavigationItemActive } from "@/lib/navigation";

export function Topbar() {
  const pathname = usePathname();
  const current = navigationItems.find((item) => isNavigationItemActive(pathname, item.href));

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur md:px-8">
      <div className="flex min-w-0 items-center gap-2 text-sm">
        <span className="font-medium text-foreground">{current?.label ?? "工作台"}</span>
        {pathname !== "/" ? <IconChevronRight className="shrink-0 text-muted-foreground" size={15} stroke={1.8} /> : null}
        {pathname !== "/" ? <span className="truncate text-muted-foreground">当前视图</span> : null}
      </div>
      <Button asChild size="sm" className="shrink-0">
        <Link href="/projects/new">
          <IconPlus size={16} stroke={1.8} />
          <span className="hidden sm:inline">新建项目</span>
        </Link>
      </Button>
    </header>
  );
}
