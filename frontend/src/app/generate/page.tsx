"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Database, FileText, Users } from "lucide-react";
import { api } from "@/lib/api";
import type { UserResponse } from "@/lib/types";
import { MacShell, type NavItem } from "@/components/mac-shell";
import { GenerateView } from "@/components/generate-view";
import { CscAdminView } from "@/components/csc-admin-view";
import { AdminUsersView } from "@/components/admin-users-view";
import { AdminUsageView } from "@/components/admin-usage-view";

type View = "generate" | "csc" | "users" | "usage";

const VIEW_META: Record<View, { title: string; subtitle: string }> = {
  generate: { title: "產生會議記錄", subtitle: "鋼筋採購週會" },
  csc: { title: "中鋼盤價管理", subtitle: "八.1 月盤 / 八.2 季盤" },
  users: { title: "帳號管理", subtitle: "建立 / 停用 / 刪除使用者" },
  usage: { title: "使用流量", subtitle: "各帳號呼叫統計" },
};

/**
 * Single-page app shell that hosts all views.
 *
 * Mount strategy: every view is rendered once and toggled with display:
 * none/block so in-flight form state survives sidebar clicks. The admin
 * views only mount when the current user is admin — non-admins never see
 * them in the DOM, and the backend rejects the underlying APIs anyway.
 */
export default function AppPage() {
  const [view, setView] = useState<View>("generate");
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<UserResponse>("/api/auth/me"),
  });
  const isAdmin = me?.role === "admin";

  const navItems: NavItem[] = [
    {
      id: "generate",
      label: "產生會議記錄",
      icon: FileText,
      onClick: () => setView("generate"),
    },
    {
      id: "csc",
      label: "中鋼盤價管理",
      icon: Database,
      onClick: () => setView("csc"),
    },
    ...(isAdmin
      ? [
          {
            id: "users",
            label: "帳號管理",
            icon: Users,
            onClick: () => setView("users"),
          } satisfies NavItem,
          {
            id: "usage",
            label: "使用流量",
            icon: Activity,
            onClick: () => setView("usage"),
          } satisfies NavItem,
        ]
      : []),
  ];

  // If a non-admin somehow lands on an admin view (stale link), bounce back.
  const effectiveView: View =
    !isAdmin && (view === "users" || view === "usage") ? "generate" : view;
  const meta = VIEW_META[effectiveView];

  return (
    <MacShell
      title={meta.title}
      pageSubtitle={meta.subtitle}
      activeNav={effectiveView}
      navItems={navItems}
    >
      <div style={{ display: effectiveView === "generate" ? "block" : "none" }}>
        <GenerateView />
      </div>
      <div style={{ display: effectiveView === "csc" ? "block" : "none" }}>
        <CscAdminView />
      </div>
      {isAdmin && (
        <>
          <div style={{ display: effectiveView === "users" ? "block" : "none" }}>
            <AdminUsersView />
          </div>
          <div style={{ display: effectiveView === "usage" ? "block" : "none" }}>
            <AdminUsageView />
          </div>
        </>
      )}
    </MacShell>
  );
}
