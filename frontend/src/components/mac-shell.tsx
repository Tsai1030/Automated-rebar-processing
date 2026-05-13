"use client";

import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Image from "next/image";
import {
  Database,
  FileText,
  LogOut,
  type LucideIcon,
} from "lucide-react";
import { type ReactNode } from "react";
import { api } from "@/lib/api";
import type { UserResponse } from "@/lib/types";

/**
 * macOS-styled application window: title bar with traffic lights (decorative),
 * left sidebar with sectioned navigation, main content area with optional
 * page header.
 *
 * Implementation notes:
 *   - Traffic lights are non-functional (would close the browser tab) but
 *     serve as a strong visual anchor that this is "an app", not a webpage.
 *   - Sidebar uses backdrop-filter for vibrancy effect over the body's
 *     subtle gradient background.
 *   - Width is capped to 1280px and centred — matches macOS HIG for utility
 *     apps; comfortable on a 13" MacBook and larger monitors alike.
 */

export interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
  onClick: () => void;
  badge?: string;
}

interface MacShellProps {
  /** Title shown in the title bar (also used as window name). */
  title: string;
  /** Active nav item id — controls sidebar highlight. */
  activeNav: string;
  navItems: NavItem[];
  children: ReactNode;
  /** Optional small text under title bar (e.g. file path / breadcrumb). */
  pageSubtitle?: string;
}

export function MacShell({
  title,
  activeNav,
  navItems,
  children,
  pageSubtitle,
}: MacShellProps) {
  const router = useRouter();
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<UserResponse>("/api/auth/me"),
  });

  const logout = async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch {
      /* ignore */
    }
    router.push("/login");
    router.refresh();
  };

  return (
    <div className="h-screen flex items-stretch justify-center px-2 py-2 sm:px-6 sm:py-6 overflow-hidden">
      <div
        className="w-full max-w-[1280px] flex flex-col window-in overflow-hidden"
        style={{
          background: "var(--surface-window)",
          borderRadius: "var(--radius-window)",
          boxShadow: "var(--shadow-window)",
          // height auto-fills the flex container (h-screen minus padding).
          // Cap on extra-tall monitors so the window stops growing.
          maxHeight: "920px",
        }}
      >
        {/* ── Title bar ── */}
        <div
          className="flex items-center px-3 sm:px-4 h-11 border-b"
          style={{
            background: "var(--surface-titlebar)",
            backdropFilter: "blur(20px) saturate(180%)",
            WebkitBackdropFilter: "blur(20px) saturate(180%)",
            borderColor: "var(--border-subtle)",
          }}
        >
          <TrafficLights />
          <div className="flex-1 text-center select-none min-w-0 px-2">
            <span
              className="text-[13px] font-medium truncate"
              style={{ color: "var(--text-primary)" }}
            >
              {title}
            </span>
            {pageSubtitle && (
              <span
                className="ml-2 text-[12px] hidden sm:inline"
                style={{ color: "var(--text-tertiary)" }}
              >
                — {pageSubtitle}
              </span>
            )}
          </div>
          <div className="w-[40px] sm:w-[68px]" /> {/* symmetry spacer */}
        </div>

        {/* ── Mobile-only top nav (replaces sidebar) ── */}
        <MobileTopNav
          activeNav={activeNav}
          navItems={navItems}
          me={me}
          onLogout={logout}
        />

        {/* ── Body: sidebar + main ──
            min-h-0 is critical so the inner <main> can shrink and scroll.
            pr-0.5 inserts a hairline gap so the scrollbar doesn't sit
            flush against the rounded window corner. */}
        <div className="flex flex-1 min-h-0 pr-0.5">
          {/* Sidebar — desktop only */}
          <aside
            className="hidden sm:flex w-[220px] flex-col border-r select-none"
            style={{
              background: "var(--surface-sidebar)",
              backdropFilter: "blur(40px) saturate(180%)",
              WebkitBackdropFilter: "blur(40px) saturate(180%)",
              borderColor: "var(--border-subtle)",
            }}
          >
            {/* App identity */}
            <div className="px-4 pt-5 pb-3">
              <div className="flex items-center gap-2.5">
                <Image
                  src="/logo.png"
                  alt="BES logo"
                  width={36}
                  height={36}
                  className="shrink-0"
                />
                <div className="leading-tight">
                  <div
                    className="text-[16px] font-semibold tracking-tight"
                    style={{ color: "var(--text-primary)" }}
                  >
                    鋼筋會議
                  </div>
                  <div
                    className="text-[12px] mt-0.5"
                    style={{ color: "var(--text-tertiary)" }}
                  >
                    自動化系統
                  </div>
                </div>
              </div>
            </div>

            <SidebarSection label="工作流程" />
            <nav className="flex flex-col px-2 gap-px">
              {navItems.map((item) => (
                <SidebarItem
                  key={item.id}
                  item={item}
                  active={item.id === activeNav}
                />
              ))}
            </nav>

            <div className="flex-1" />

            {/* User block */}
            <div
              className="m-2 p-2.5 rounded-md flex items-center gap-2"
              style={{ background: "var(--surface-hover)" }}
            >
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-[12px] font-semibold"
                style={{
                  background: "var(--accent-soft)",
                  color: "var(--accent)",
                }}
              >
                {(me?.username ?? "?").charAt(0).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0">
                <div
                  className="text-[12px] font-medium truncate"
                  style={{ color: "var(--text-primary)" }}
                >
                  {me?.username ?? "—"}
                </div>
                <div
                  className="text-[10px] truncate"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  {me?.role ?? "user"}
                </div>
              </div>
              <button
                onClick={logout}
                className="p-1.5 rounded transition-colors hover:bg-black/5"
                title="登出"
              >
                <LogOut
                  className="w-3.5 h-3.5"
                  style={{ color: "var(--text-secondary)" }}
                />
              </button>
            </div>
          </aside>

          {/* Main content */}
          <main className="flex-1 overflow-auto">
            <div className="px-4 py-5 sm:px-10 sm:py-8">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}

/**
 * Compact horizontal nav shown only on mobile, replacing the desktop sidebar.
 * Sits between title bar and main content. Scrolls horizontally if many
 * nav items overflow the viewport.
 */
function MobileTopNav({
  activeNav,
  navItems,
  me,
  onLogout,
}: {
  activeNav: string;
  navItems: NavItem[];
  me: UserResponse | undefined;
  onLogout: () => void;
}) {
  return (
    <div
      className="flex sm:hidden items-center gap-1.5 px-3 py-2 border-b overflow-x-auto"
      style={{
        background: "var(--surface-sidebar)",
        backdropFilter: "blur(40px) saturate(180%)",
        WebkitBackdropFilter: "blur(40px) saturate(180%)",
        borderColor: "var(--border-subtle)",
      }}
    >
      {navItems.map((item) => {
        const Icon = item.icon;
        const active = item.id === activeNav;
        return (
          <button
            key={item.id}
            onClick={item.onClick}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] font-medium whitespace-nowrap transition-colors shrink-0"
            style={
              active
                ? {
                    background: "var(--surface-card)",
                    color: "var(--text-primary)",
                    boxShadow:
                      "0 0 0 0.5px oklch(0% 0 0 / 0.06), 0 1px 2px oklch(0% 0 0 / 0.05)",
                  }
                : { color: "var(--text-secondary)" }
            }
          >
            <Icon
              className="w-3.5 h-3.5 shrink-0"
              style={{
                color: active ? "var(--accent)" : "var(--text-tertiary)",
              }}
            />
            <span>{item.label}</span>
          </button>
        );
      })}
      <div className="flex-1 min-w-2" />
      <button
        onClick={onLogout}
        className="flex items-center gap-1 px-2 py-1.5 rounded-md text-[12px] shrink-0"
        style={{ color: "var(--text-tertiary)" }}
        title="登出"
      >
        <LogOut className="w-3.5 h-3.5" />
        <span className="sr-only">登出</span>
        <span className="hidden xs:inline">{me?.username ?? ""}</span>
      </button>
    </div>
  );
}

/** Brand wordmark in place of the macOS traffic lights — same vertical
 *  rhythm so the title bar layout stays balanced. */
function TrafficLights() {
  return <BrandMark />;
}

function BrandMark() {
  return (
    <span
      className="select-none"
      style={{
        fontFamily:
          'ui-monospace, SFMono-Regular, "SF Mono", Menlo, "Cascadia Mono", monospace',
        fontWeight: 800,
        fontSize: "14px",
        letterSpacing: "0.06em",
        lineHeight: 1,
        color: "var(--accent)",
      }}
    >
      BES
    </span>
  );
}

function SidebarSection({ label }: { label: string }) {
  return (
    <div
      className="px-4 mt-4 mb-1.5 text-[10px] font-semibold uppercase tracking-wider select-none"
      style={{ color: "var(--text-tertiary)" }}
    >
      {label}
    </div>
  );
}

function SidebarItem({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <button
      onClick={item.onClick}
      className="flex items-center gap-2 px-2.5 py-1.5 text-[13px] rounded-md transition-colors text-left"
      style={
        active
          ? {
              background: "var(--surface-selected)",
              color: "var(--text-primary)",
            }
          : { color: "var(--text-secondary)" }
      }
      onMouseEnter={(e) => {
        if (!active)
          e.currentTarget.style.background = "var(--surface-hover)";
      }}
      onMouseLeave={(e) => {
        if (!active) e.currentTarget.style.background = "transparent";
      }}
    >
      <Icon
        className="w-4 h-4 shrink-0"
        style={{ color: active ? "var(--accent)" : "var(--text-tertiary)" }}
      />
      <span className="flex-1 truncate">{item.label}</span>
      {item.badge && (
        <span
          className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
          style={{
            background: "var(--accent-soft)",
            color: "var(--accent)",
          }}
        >
          {item.badge}
        </span>
      )}
    </button>
  );
}

/* Re-export commonly used icons so consumers don't have to import lucide */
export { Database as DatabaseIcon, FileText as FileTextIcon };
