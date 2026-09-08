"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IconAdjustmentsHorizontal,
  IconFileText,
  IconFolder,
  IconLayoutDashboard,
  IconMap2,
  IconSettings,
} from "@tabler/icons-react";
import { cn } from "@ue-agent/ui/lib/cn";
import { isNavigationItemActive } from "@/lib/navigation";

export const navigationItems = [
  { label: "工作台", href: "/", icon: IconLayoutDashboard },
  { label: "项目", href: "/projects", icon: IconFolder },
  { label: "U1 城市选址", href: "/u1", icon: IconMap2 },
  { label: "政策资料", href: "/policies", icon: IconFileText },
  { label: "系统设置", href: "/settings", icon: IconSettings },
] as const;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-border bg-surface md:flex">
      <div className="flex h-14 items-center gap-3 border-b border-border px-5">
        <div className="flex size-8 items-center justify-center rounded-md bg-primary text-sm font-semibold text-white">U</div>
        <div>
          <p className="text-sm font-semibold tracking-tight">UE-Agent</p>
          <p className="text-[11px] text-muted-foreground">决策测算工作台</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 p-3" aria-label="主导航">
        <p className="px-3 pb-2 pt-2 text-[11px] font-semibold tracking-[0.08em] text-muted-foreground">工作空间</p>
        {navigationItems.slice(0, 3).map((item) => {
          const Icon = item.icon;
          const active = isNavigationItemActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
                active ? "bg-surface-selected text-primary" : "text-muted-foreground hover:bg-surface-subtle hover:text-foreground",
              )}
              aria-current={active ? "page" : undefined}
            >
              <Icon size={18} stroke={1.8} />
              <span>{item.label}</span>
            </Link>
          );
        })}
        <p className="px-3 pb-2 pt-6 text-[11px] font-semibold tracking-[0.08em] text-muted-foreground">资料与管理</p>
        {navigationItems.slice(3).map((item) => {
          const Icon = item.icon;
          const active = isNavigationItemActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors",
                active ? "bg-surface-selected text-primary" : "text-muted-foreground hover:bg-surface-subtle hover:text-foreground",
              )}
              aria-current={active ? "page" : undefined}
            >
              <Icon size={18} stroke={1.8} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border p-4">
        <div className="flex items-center gap-3 rounded-md bg-surface-subtle px-3 py-2.5">
          <div className="flex size-8 items-center justify-center rounded-full bg-primary-subtle text-xs font-semibold text-primary">JH</div>
          <div className="min-w-0">
            <p className="truncate text-xs font-medium">当前工作区</p>
            <p className="truncate text-[11px] text-muted-foreground">本地开发环境</p>
          </div>
          <IconAdjustmentsHorizontal className="ml-auto text-muted-foreground" size={16} stroke={1.8} />
        </div>
      </div>
    </aside>
  );
}
