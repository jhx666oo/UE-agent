import { IconBuilding, IconFileText, IconLayoutDashboard, IconSettings } from "@tabler/icons-react";

export const primaryNavigation = [
  { label: "总览", href: "/", icon: IconLayoutDashboard },
  { label: "城市项目", href: "/projects", icon: IconBuilding },
  { label: "政策资料", href: "/policies", icon: IconFileText },
  { label: "参数设置", href: "/settings", icon: IconSettings },
] as const;

function normalizePath(path: string) {
  if (path === "/") return "/";
  return path.replace(/\/+$/, "");
}

export function isNavigationItemActive(pathname: string, href: string) {
  const currentPath = normalizePath(pathname);
  const targetPath = normalizePath(href);

  if (targetPath === "/") return currentPath === "/";
  return currentPath === targetPath || currentPath.startsWith(`${targetPath}/`);
}
