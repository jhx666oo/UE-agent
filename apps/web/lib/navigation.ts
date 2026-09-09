import { IconChartArcs, IconBuilding, IconFileText, IconLayoutDashboard } from "@tabler/icons-react";

export const primaryNavigation = [
  { label: "总览", href: "/", icon: IconLayoutDashboard },
  { label: "城市测算", href: "/projects", icon: IconBuilding },
  { label: "政策资料", href: "/policies", icon: IconFileText },
  { label: "城市对比", href: "/?scope=compare", icon: IconChartArcs },
] as const;

function normalizePath(path: string) {
  if (path === "/") return "/";
  return path.replace(/\/+$/, "");
}

export function isNavigationItemActive(pathname: string, href: string) {
  const currentPath = normalizePath(pathname);
  const targetPath = normalizePath(href.split("?")[0]);

  if (targetPath === "/") return currentPath === "/";
  return currentPath === targetPath || currentPath.startsWith(`${targetPath}/`);
}
