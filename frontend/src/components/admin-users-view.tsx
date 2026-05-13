"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  KeyRound,
  Plus,
  ShieldCheck,
  Trash2,
  UserPlus,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type {
  AdminUser,
  CreateUserRequest,
  ResetPasswordRequest,
  UpdateUserRequest,
  UserResponse,
} from "@/lib/types";

const USERS_KEY = ["admin", "users"] as const;

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("zh-TW", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AdminUsersView() {
  const qc = useQueryClient();
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<UserResponse>("/api/auth/me"),
  });
  const { data: users, isLoading } = useQuery<AdminUser[]>({
    queryKey: USERS_KEY,
    queryFn: () => api<AdminUser[]>("/api/admin/users"),
  });

  const [showCreate, setShowCreate] = useState(false);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);

  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: UpdateUserRequest }) =>
      api(`/api/admin/users/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: USERS_KEY }),
  });

  const del = useMutation({
    mutationFn: (id: number) =>
      api(`/api/admin/users/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: USERS_KEY }),
  });

  return (
    <>
      <div className="max-w-3xl">
        <div
          className="text-[10px] font-semibold uppercase tracking-[0.12em]"
          style={{ color: "var(--accent)" }}
        >
          ADMIN
        </div>
        <h1
          className="mt-1.5 text-[22px] sm:text-[28px] font-semibold tracking-tight leading-tight"
          style={{ color: "var(--text-primary)" }}
        >
          帳號管理
        </h1>
        <p
          className="mt-2 text-[13px] sm:text-[14px] leading-relaxed"
          style={{ color: "var(--text-secondary)" }}
        >
          只有 admin 可以新增、停用或刪除帳號。停用後該帳號無法登入。
        </p>
      </div>

      <div className="mt-6 sm:mt-8">
        <section
          className="overflow-hidden"
          style={{
            background: "var(--surface-card)",
            borderRadius: "var(--radius-card)",
            boxShadow: "var(--shadow-card)",
          }}
        >
          <div
            className="px-4 sm:px-6 pt-4 sm:pt-5 pb-4 flex items-center justify-between border-b"
            style={{ borderColor: "var(--border-subtle)" }}
          >
            <div>
              <div
                className="text-[10px] font-semibold uppercase tracking-[0.12em]"
                style={{ color: "var(--text-tertiary)" }}
              >
                USERS
              </div>
              <h2
                className="mt-0.5 text-[15px] font-semibold"
                style={{ color: "var(--text-primary)" }}
              >
                帳號清單
              </h2>
            </div>
            <button
              onClick={() => setShowCreate(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium transition-colors"
              style={{
                background: "var(--accent)",
                color: "white",
                borderRadius: "var(--radius-control)",
              }}
            >
              <UserPlus className="w-3.5 h-3.5" />
              新增帳號
            </button>
          </div>

          {isLoading ? (
            <div
              className="p-6 text-[13px]"
              style={{ color: "var(--text-tertiary)" }}
            >
              載入中…
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr
                    className="text-left"
                    style={{
                      background: "var(--surface-hover)",
                      color: "var(--text-tertiary)",
                    }}
                  >
                    <Th>帳號</Th>
                    <Th>角色</Th>
                    <Th>狀態</Th>
                    <Th>上次登入</Th>
                    <Th>建立於</Th>
                    <Th className="text-right pr-6">操作</Th>
                  </tr>
                </thead>
                <tbody>
                  {(users ?? []).map((u) => {
                    const isMe = me?.id === u.id;
                    return (
                      <tr
                        key={u.id}
                        style={{ borderTop: "1px solid var(--border-subtle)" }}
                      >
                        <Td className="font-medium">
                          {u.username}
                          {isMe && (
                            <span
                              className="ml-2 text-[10px] px-1.5 py-0.5 rounded-full"
                              style={{
                                background: "var(--accent-soft)",
                                color: "var(--accent)",
                              }}
                            >
                              你
                            </span>
                          )}
                        </Td>
                        <Td>
                          <RoleBadge role={u.role} />
                        </Td>
                        <Td>
                          <StatusBadge active={u.is_active} />
                        </Td>
                        <Td className="tabular-nums">
                          {fmtDateTime(u.last_login)}
                        </Td>
                        <Td className="tabular-nums">
                          {fmtDateTime(u.created_at)}
                        </Td>
                        <Td className="text-right pr-6">
                          <div className="inline-flex items-center gap-1.5">
                            <IconBtn
                              title={
                                u.role === "admin"
                                  ? "改為一般使用者"
                                  : "升為管理員"
                              }
                              disabled={isMe && u.role === "admin"}
                              onClick={() =>
                                update.mutate({
                                  id: u.id,
                                  body: {
                                    role:
                                      u.role === "admin" ? "user" : "admin",
                                  },
                                })
                              }
                            >
                              <ShieldCheck className="w-3.5 h-3.5" />
                            </IconBtn>
                            <IconBtn
                              title={u.is_active ? "停用" : "啟用"}
                              disabled={isMe}
                              onClick={() =>
                                update.mutate({
                                  id: u.id,
                                  body: { is_active: !u.is_active },
                                })
                              }
                            >
                              {u.is_active ? (
                                <X className="w-3.5 h-3.5" />
                              ) : (
                                <Check className="w-3.5 h-3.5" />
                              )}
                            </IconBtn>
                            <IconBtn
                              title="重設密碼"
                              onClick={() => setResetTarget(u)}
                            >
                              <KeyRound className="w-3.5 h-3.5" />
                            </IconBtn>
                            <IconBtn
                              title="刪除"
                              danger
                              disabled={isMe}
                              onClick={() => {
                                if (
                                  confirm(
                                    `確定要刪除「${u.username}」嗎？此操作不可復原。`,
                                  )
                                )
                                  del.mutate(u.id);
                              }}
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </IconBtn>
                          </div>
                        </Td>
                      </tr>
                    );
                  })}
                  {(users ?? []).length === 0 && (
                    <tr>
                      <td
                        colSpan={6}
                        className="px-6 py-8 text-center text-[13px]"
                        style={{ color: "var(--text-tertiary)" }}
                      >
                        尚無帳號
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {update.error && (
            <ErrorBar message={(update.error as Error).message} />
          )}
          {del.error && <ErrorBar message={(del.error as Error).message} />}
        </section>
      </div>

      {showCreate && (
        <CreateUserDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            qc.invalidateQueries({ queryKey: USERS_KEY });
          }}
        />
      )}

      {resetTarget && (
        <ResetPasswordDialog
          user={resetTarget}
          onClose={() => setResetTarget(null)}
        />
      )}
    </>
  );
}

function Th({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-4 py-2 font-medium text-[11px] uppercase tracking-wider ${className}`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <td
      className={`px-4 py-2 ${className}`}
      style={{ color: "var(--text-primary)" }}
    >
      {children}
    </td>
  );
}

function RoleBadge({ role }: { role: "admin" | "user" }) {
  const isAdmin = role === "admin";
  return (
    <span
      className="inline-flex items-center text-[11px] px-2 py-0.5 rounded-full font-medium"
      style={{
        background: isAdmin ? "var(--accent-soft)" : "var(--surface-hover)",
        color: isAdmin ? "var(--accent)" : "var(--text-secondary)",
      }}
    >
      {isAdmin ? "admin" : "user"}
    </span>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full font-medium"
      style={{
        background: active
          ? "oklch(95% 0.06 145)"
          : "oklch(95% 0.03 27)",
        color: active ? "var(--status-success)" : "var(--status-error)",
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{
          background: active
            ? "var(--status-success)"
            : "var(--status-error)",
        }}
      />
      {active ? "啟用" : "停用"}
    </span>
  );
}

function IconBtn({
  children,
  title,
  onClick,
  disabled = false,
  danger = false,
}: {
  children: React.ReactNode;
  title: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      title={title}
      disabled={disabled}
      onClick={onClick}
      className="p-1.5 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
      style={{
        color: danger ? "var(--status-error)" : "var(--text-secondary)",
      }}
      onMouseEnter={(e) => {
        if (!disabled)
          e.currentTarget.style.background = "var(--surface-hover)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
      }}
    >
      {children}
    </button>
  );
}

function ErrorBar({ message }: { message: string }) {
  return (
    <div
      className="px-4 py-2 text-[12px] border-t"
      style={{
        borderColor: "var(--border-subtle)",
        color: "var(--status-error)",
      }}
    >
      {message}
    </div>
  );
}

function CreateUserDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "user">("user");

  const create = useMutation({
    mutationFn: (body: CreateUserRequest) =>
      api("/api/admin/users", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: onCreated,
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    create.mutate({ username, password, role });
  };

  const errMsg =
    create.error instanceof ApiError
      ? typeof create.error.body === "object" && create.error.body !== null
        ? // FastAPI default error shape: { detail: "..." }
          ((create.error.body as { detail?: string }).detail ??
          create.error.message)
        : create.error.message
      : (create.error as Error | null)?.message;

  return (
    <Modal title="新增帳號" onClose={onClose} icon={<Plus className="w-4 h-4" />}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <ModalField label="帳號">
          <input
            type="text"
            required
            minLength={3}
            maxLength={64}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            className="w-full px-3 py-2 text-[13px] outline-none"
            style={inputStyle}
          />
        </ModalField>
        <ModalField label="密碼（至少 8 字元）">
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 text-[13px] outline-none"
            style={inputStyle}
          />
        </ModalField>
        <ModalField label="角色">
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as "admin" | "user")}
            className="w-full px-3 py-2 text-[13px] outline-none"
            style={inputStyle}
          >
            <option value="user">user（一般使用者）</option>
            <option value="admin">admin（管理員）</option>
          </select>
        </ModalField>

        {errMsg && (
          <div
            className="text-[12px] px-3 py-2 rounded-md"
            style={{
              background: "oklch(96% 0.04 27)",
              color: "var(--status-error)",
            }}
          >
            {errMsg}
          </div>
        )}

        <div className="flex justify-end gap-2 mt-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-[13px]"
            style={{
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-control)",
              color: "var(--text-secondary)",
            }}
          >
            取消
          </button>
          <button
            type="submit"
            disabled={create.isPending}
            className="px-3 py-1.5 text-[13px] font-medium disabled:opacity-50"
            style={{
              background: "var(--accent)",
              color: "white",
              borderRadius: "var(--radius-control)",
            }}
          >
            {create.isPending ? "建立中…" : "建立"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ResetPasswordDialog({
  user,
  onClose,
}: {
  user: AdminUser;
  onClose: () => void;
}) {
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);

  const reset = useMutation({
    mutationFn: (body: ResetPasswordRequest) =>
      api(`/api/admin/users/${user.id}/password`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => setDone(true),
  });

  return (
    <Modal
      title={`重設「${user.username}」的密碼`}
      onClose={onClose}
      icon={<KeyRound className="w-4 h-4" />}
    >
      {done ? (
        <div className="flex flex-col gap-3">
          <div
            className="text-[13px] px-3 py-2 rounded-md inline-flex items-center gap-1.5"
            style={{
              background: "oklch(96% 0.06 145)",
              color: "var(--status-success)",
            }}
          >
            <Check className="w-3.5 h-3.5" />
            密碼已更新
          </div>
          <div className="flex justify-end">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-[13px] font-medium"
              style={{
                background: "var(--accent)",
                color: "white",
                borderRadius: "var(--radius-control)",
              }}
            >
              關閉
            </button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            reset.mutate({ password });
          }}
          className="flex flex-col gap-3"
        >
          <ModalField label="新密碼（至少 8 字元）">
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoFocus
              className="w-full px-3 py-2 text-[13px] outline-none"
              style={inputStyle}
            />
          </ModalField>
          {reset.error && (
            <div
              className="text-[12px] px-3 py-2 rounded-md"
              style={{
                background: "oklch(96% 0.04 27)",
                color: "var(--status-error)",
              }}
            >
              {(reset.error as Error).message}
            </div>
          )}
          <div className="flex justify-end gap-2 mt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-[13px]"
              style={{
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-control)",
                color: "var(--text-secondary)",
              }}
            >
              取消
            </button>
            <button
              type="submit"
              disabled={reset.isPending}
              className="px-3 py-1.5 text-[13px] font-medium disabled:opacity-50"
              style={{
                background: "var(--accent)",
                color: "white",
                borderRadius: "var(--radius-control)",
              }}
            >
              {reset.isPending ? "更新中…" : "更新密碼"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}

const inputStyle: React.CSSProperties = {
  background: "var(--surface-input)",
  border: "1px solid var(--border-subtle)",
  borderRadius: "var(--radius-control)",
  color: "var(--text-primary)",
};

function Modal({
  title,
  icon,
  onClose,
  children,
}: {
  title: string;
  icon?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      style={{ background: "oklch(0% 0 0 / 0.35)" }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-[420px] overflow-hidden window-in"
        style={{
          background: "var(--surface-window)",
          borderRadius: "var(--radius-window)",
          boxShadow: "var(--shadow-window)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center justify-between px-4 h-11 border-b"
          style={{
            background: "var(--surface-titlebar)",
            borderColor: "var(--border-subtle)",
          }}
        >
          <div
            className="flex items-center gap-2 text-[13px] font-medium"
            style={{ color: "var(--text-primary)" }}
          >
            {icon}
            {title}
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded hover:bg-black/5"
            title="關閉"
          >
            <X
              className="w-4 h-4"
              style={{ color: "var(--text-secondary)" }}
            />
          </button>
        </div>
        <div className="px-5 py-5">{children}</div>
      </div>
    </div>
  );
}

function ModalField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span
        className="text-[11px] font-medium"
        style={{ color: "var(--text-secondary)" }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}
