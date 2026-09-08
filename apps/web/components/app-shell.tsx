"use client";

import type { ReactNode } from "react";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";

export function AppShell({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <div className="min-w-0 md:pl-60">
        <Topbar />
        <main className="page-container py-6 sm:py-8">{children}</main>
      </div>
    </div>
  );
}
