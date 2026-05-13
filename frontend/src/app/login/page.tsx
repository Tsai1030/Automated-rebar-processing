"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api, ApiError } from "@/lib/api";
import type { LoginResponse } from "@/lib/types";

const loginSchema = z.object({
  username: z.string().min(1, "請輸入帳號"),
  password: z.string().min(1, "請輸入密碼"),
});
type LoginForm = z.infer<typeof loginSchema>;

/**
 * IMPORTANT: useSearchParams() must live inside a <Suspense> boundary in
 * Next.js 16 / React 19. Otherwise client hydration is deferred and an
 * early form submit falls back to native HTML — which means GET with
 * credentials in the URL. We split the page into a thin shell with the
 * Suspense boundary and the actual form lives below.
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
    <main className="flex min-h-screen flex-1 items-center justify-center px-4">
      <div className="text-sm text-gray-500">載入中…</div>
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
    <main className="flex min-h-screen flex-1 items-center justify-center px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-sm ring-1 ring-gray-200">
        <h1 className="text-2xl font-semibold text-gray-900">登入</h1>
        <p className="mt-1 text-sm text-gray-500">鋼筋會議記錄自動化系統</p>

        <form
          method="post"
          action="javascript:void(0)"
          onSubmit={(e) => {
            // Defense in depth: kill native submission *before* RHF runs.
            // If JS hasn't hydrated yet, method="post" + action="void(0)"
            // still keeps the password out of the URL.
            e.preventDefault();
            void handleSubmit(onSubmit)(e);
          }}
          className="mt-8 space-y-5"
        >
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700">
              帳號
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              {...register("username")}
            />
            {errors.username && (
              <p className="mt-1 text-xs text-red-600">{errors.username.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700">
              密碼
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              {...register("password")}
            />
            {errors.password && (
              <p className="mt-1 text-xs text-red-600">{errors.password.message}</p>
            )}
          </div>

          {serverError && (
            <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
              {serverError}
            </div>
          )}

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? "登入中…" : "登入"}
          </button>
        </form>

        <p className="mt-6 text-xs text-gray-400">
          首次使用？請聯絡管理員建立帳號（或呼叫 <code>/api/admin/bootstrap</code> 建立第一位管理員）
        </p>
      </div>
    </main>
  );
}
