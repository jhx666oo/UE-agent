"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  IconAdjustmentsHorizontal,
} from "@tabler/icons-react";
import { cn } from "@ue-agent/ui/lib/cn";
import { isNavigationItemActive, primaryNavigation } from "@/lib/navigation";

export const navigationItems = primaryNavigation;

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-border bg-surface md:flex">
      <div className="flex h-14 items-center gap-3 border-b border-border px-5">
        <div className="flex size-8 items-center justify-center rounded-md bg-primary text-sm font-semibold text-primary-foreground">U</div>
        <div>
          <p className="text-sm font-semibold tracking-tight">UE-Agent</p>
          <p className="text-[11px] text-muted-foreground">长护险决策总览</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 p-3" aria-label="主导航">
        {navigationItems.map((item) => {
          const Icon = item.icon;
          const active = isNavigationItemActive(pathname, item.href);
          return (
            <Link
              key={item.label}
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
            <p className="truncate text-[11px] text-muted-foreground">本地开发环境 · Demo</p>
          </div>
          <IconAdjustmentsHorizontal className="ml-auto text-muted-foreground" size={16} stroke={1.8} />
        </div>
      </div>
    </aside>
  );
}
