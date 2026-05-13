"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Image from "next/image";
import { ArrowRight } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { LoginResponse } from "@/lib/types";

const loginSchema = z.object({
  username: z.string().min(1, "請輸入帳號"),
  password: z.string().min(1, "請輸入密碼"),
});
type LoginForm = z.infer<typeof loginSchema>;

/**
 * macOS-style sign-in window — visually evokes the system login screen:
 *   - Wallpaper background with a soft mesh
 *   - Rounded translucent window centred on screen
 *   - Window chrome (traffic lights, decorative)
 *   - Avatar bubble at the top of the form, name beneath
 *   - Field-only inputs (Apple HIG: no boxes for password fields, just lines)
 *
 * Suspense boundary around useSearchParams to keep early form submits from
 * leaking the password into the URL on Next.js 16's stricter hydration.
 */
export default function LoginPage() {
  return (
    <Suspense fallback={<LoginLoading />}>
      <LoginForm />
    </Suspense>
  );
}

function LoginLoading() {
  return (
    <main className="min-h-screen flex items-center justify-center">
      <div
        className="text-[13px]"
        style={{ color: "var(--text-tertiary)" }}
      >
        載入中…
      </div>
    </main>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectTo = searchParams.get("redirect") ?? "/generate";
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: "", password: "" },
  });

  const onSubmit = async (data: LoginForm) => {
    setServerError(null);
    try {
      await api<LoginResponse>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
      });
      router.push(redirectTo);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(
          err.status === 401 ? "帳號或密碼錯誤" : `登入失敗 (${err.status})`,
        );
      } else {
        setServerError("無法連線到伺服器");
      }
    }
  };

  return (
    <main
      className="min-h-screen flex items-center justify-center px-4"
      style={{
        // Soft wallpaper-like background mesh in macOS Sequoia palette
        background: `
          radial-gradient(ellipse 60% 80% at 20% 10%, oklch(85% 0.10 256 / 0.55), transparent),
          radial-gradient(ellipse 50% 60% at 80% 20%, oklch(80% 0.10 290 / 0.45), transparent),
          radial-gradient(ellipse 70% 50% at 50% 100%, oklch(82% 0.08 30 / 0.40), transparent),
          oklch(96% 0.005 250)
        `,
      }}
    >
      <div
        className="w-full max-w-[380px] window-in overflow-hidden"
        style={{
          background: "var(--surface-window)",
          borderRadius: "var(--radius-window)",
          boxShadow: "var(--shadow-window)",
        }}
      >
        {/* Title bar */}
        <div
          className="flex items-center px-4 h-10 border-b"
          style={{
            background: "var(--surface-titlebar)",
            backdropFilter: "blur(20px) saturate(180%)",
            WebkitBackdropFilter: "blur(20px) saturate(180%)",
            borderColor: "var(--border-subtle)",
          }}
        >
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
          <div className="flex-1 text-center">
            <span
              className="text-[12px] font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              登入
            </span>
          </div>
          <div className="w-[68px]" />
        </div>

        {/* Form body */}
        <div className="px-8 pt-8 pb-7 flex flex-col items-center">
          {/* Logo */}
          <Image
            src="/logo.png"
            alt="BES logo"
            width={84}
            height={84}
            preload
          />

          {/* App name */}
          <h1
            className="mt-4 text-[17px] font-semibold tracking-tight"
            style={{ color: "var(--text-primary)" }}
          >
            鋼筋會議自動化系統
          </h1>
          <p
            className="mt-1 text-[12px]"
            style={{ color: "var(--text-tertiary)" }}
          >
            請輸入您的帳號與密碼
          </p>

          <form
            method="post"
            action="javascript:void(0)"
            onSubmit={(e) => {
              e.preventDefault();
              void handleSubmit(onSubmit)(e);
            }}
            className="mt-7 w-full flex flex-col gap-3"
          >
            <Field
              label="帳號"
              error={errors.username?.message}
            >
              <input
                type="text"
                autoComplete="username"
                autoFocus
                {...register("username")}
                className="w-full px-3 py-2 text-[13px] outline-none"
                style={{
                  background: "var(--surface-input)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-control)",
                  color: "var(--text-primary)",
                }}
              />
            </Field>

            <Field
              label="密碼"
              error={errors.password?.message}
            >
              <input
                type="password"
                autoComplete="current-password"
                {...register("password")}
                className="w-full px-3 py-2 text-[13px] outline-none"
                style={{
                  background: "var(--surface-input)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-control)",
                  color: "var(--text-primary)",
                }}
              />
            </Field>

            {serverError && (
              <div
                className="text-[12px] px-3 py-2 rounded-md"
                style={{
                  background: "oklch(96% 0.04 27)",
                  color: "var(--status-error)",
                }}
              >
                {serverError}
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className="mt-2 w-full flex items-center justify-center gap-2 py-2 text-[13px] font-medium transition-all disabled:opacity-60 disabled:cursor-not-allowed"
              style={{
                background: "var(--accent)",
                color: "var(--accent-text)",
                borderRadius: "var(--radius-control)",
                boxShadow: "0 1px 2px oklch(60% 0.21 256 / 0.40)",
              }}
              onMouseEnter={(e) => {
                if (!isSubmitting)
                  e.currentTarget.style.background = "var(--accent-hover)";
              }}
              onMouseLeave={(e) => {
                if (!isSubmitting)
                  e.currentTarget.style.background = "var(--accent)";
              }}
            >
              {isSubmitting ? "登入中…" : "登入"}
              {!isSubmitting && <ArrowRight className="w-3.5 h-3.5" />}
            </button>
          </form>
        </div>

        {/* Footer hint */}
        <div
          className="px-8 py-3 border-t text-[11px] text-center"
          style={{
            background: "var(--surface-titlebar)",
            borderColor: "var(--border-subtle)",
            color: "var(--text-tertiary)",
          }}
        >
          首次使用請聯絡管理員
        </div>
      </div>
    </main>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
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
      {error && (
        <span
          className="text-[11px]"
          style={{ color: "var(--status-error)" }}
        >
          {error}
        </span>
      )}
    </label>
  );
}
