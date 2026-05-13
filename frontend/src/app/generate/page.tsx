"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { api, apiBase, ApiError } from "@/lib/api";
import type {
  GenerationStartRequest,
  GenerationStatusResponse,
  InternalDataRequest,
  UserResponse,
} from "@/lib/types";
import { Stepper } from "@/components/stepper";

const STEPS = ["設定", "抓取", "補內部", "預覽", "下載"];

/** Convert ISO date string (YYYY-MM-DD) to that week's Monday in M/D form.
 *  豐興 only opens on Mondays — UI shows the derived opening date so the
 *  user sees what the system will actually fetch. Mirror of backend
 *  `opening_monday()` in `steel_backend/core/dates.py`. */
function openingMondayLabel(isoDate: string): string {
  if (!isoDate) return "—";
  const d = new Date(isoDate + "T00:00:00");
  if (Number.isNaN(d.getTime())) return "—";
  // JS getDay(): 0=Sun, 1=Mon, ..., 6=Sat. Python weekday(): 0=Mon, 6=Sun.
  // Days to subtract = (getDay()+6)%7  → Mon→0, Tue→1, ..., Sun→6
  const offset = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - offset);
  return `${d.getMonth() + 1}/${d.getDate()}（週一）`;
}

interface InternalForm {
  meeting_time: string;
  contract_remaining_tons: string;
  contract_usable_until: string;
  meeting_conclusion_last_week: string;
  meeting_conclusion_this_week: string;
}

export default function GeneratePage() {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2 | 3 | 4 | 5>(1);
  const [meetingDate, setMeetingDate] = useState(
    () => new Date().toISOString().slice(0, 10),
  );
  const [result, setResult] = useState<GenerationStatusResponse | null>(null);

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<UserResponse>("/api/auth/me"),
  });

  const runMutation = useMutation({
    mutationFn: (input: GenerationStartRequest) =>
      api<GenerationStatusResponse>("/api/generation/run", {
        method: "POST",
        body: JSON.stringify(input),
      }),
    onSuccess: (data) => {
      setResult(data);
      setStep(3);
    },
  });

  const internalForm = useForm<InternalForm>({
    defaultValues: {
      meeting_time: "17:00~17:30",
      contract_remaining_tons: "",
      contract_usable_until: "",
      meeting_conclusion_last_week: "",
      meeting_conclusion_this_week: "",
    },
  });

  const internalMutation = useMutation({
    mutationFn: async (form: InternalForm) => {
      if (!result) throw new Error("no active run");
      const payload: InternalDataRequest = {
        meeting_time: form.meeting_time,
        data: {
          contract_remaining_tons: form.contract_remaining_tons,
          contract_usable_until: form.contract_usable_until,
          meeting_conclusion_last_week: form.meeting_conclusion_last_week,
          meeting_conclusion_this_week: form.meeting_conclusion_this_week,
        },
      };
      return api<GenerationStatusResponse>(
        `/api/generation/${result.run_id}/internal-data`,
        { method: "POST", body: JSON.stringify(payload) },
      );
    },
    onSuccess: (data) => {
      setResult(data);
      setStep(5);
    },
  });

  const downloadDocx = async () => {
    if (!result) return;
    const res = await fetch(
      `${apiBase}/api/generation/${result.run_id}/docx`,
      { credentials: "include" },
    );
    if (!res.ok) {
      alert(`下載失敗: ${res.status}`);
      return;
    }
    const blob = await res.blob();
    const cd = res.headers.get("content-disposition") ?? "";
    const match = /filename\*?=(?:UTF-8'')?([^;]+)/i.exec(cd);
    const filename = match
      ? decodeURIComponent(match[1].replace(/^"|"$/g, ""))
      : `meeting_${result.run_id}.docx`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const logout = async () => {
    await api("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  };

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900">
            鋼筋會議記錄自動化系統
          </h1>
          <p className="mt-1 text-sm text-gray-500">登入者：{me?.username ?? "…"}</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => router.push("/admin/csc-prices")}
            className="rounded-lg px-3 py-1.5 text-sm text-gray-700 ring-1 ring-gray-200 hover:bg-gray-100"
          >
            中鋼盤價管理
          </button>
          <button
            onClick={logout}
            className="rounded-lg px-3 py-1.5 text-sm text-gray-600 ring-1 ring-gray-200 hover:bg-gray-100"
          >
            登出
          </button>
        </div>
      </header>

      <div className="mb-10 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
        <Stepper current={step} steps={STEPS} />
      </div>

      {step === 1 && (
        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Step 1 — 設定</h2>
          <p className="mt-1 text-sm text-gray-500">
            指定本週會議日期。豐興每週一開盤，系統會自動以該週的週一為盤價基準日。
          </p>
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-gray-700">會議日期</span>
              <input
                type="date"
                value={meetingDate}
                onChange={(e) => setMeetingDate(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </label>
            <div className="block">
              <span className="text-sm font-medium text-gray-700">
                豐興開盤日（系統自動推算）
              </span>
              <div className="mt-1 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700">
                {openingMondayLabel(meetingDate)}
              </div>
            </div>
          </div>
          <div className="mt-8 flex justify-end">
            <button
              onClick={() => setStep(2)}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              下一步：抓取盤價 →
            </button>
          </div>
        </section>
      )}

      {step === 2 && (
        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Step 2 — 抓取盤價</h2>
          <p className="mt-1 text-sm text-gray-500">
            目標：<span className="font-medium text-gray-900">{openingMondayLabel(meetingDate)}</span>
            　系統將呼叫豐興、weekly_market、market_narrator 三個來源，可能需要 30-60 秒。
          </p>
          <div className="mt-6 flex items-center gap-3">
            <button
              onClick={() => runMutation.mutate({ meeting_date: meetingDate })}
              disabled={runMutation.isPending}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
            >
              {runMutation.isPending ? "抓取中…" : "▶ 開始抓取"}
            </button>
            <button
              onClick={() => setStep(1)}
              className="rounded-lg px-3 py-2 text-sm text-gray-600 ring-1 ring-gray-200 hover:bg-gray-50"
            >
              ← 上一步
            </button>
          </div>
          {runMutation.error && (
            <p className="mt-4 text-sm text-red-600">
              抓取失敗：{(runMutation.error as Error).message}
            </p>
          )}
        </section>
      )}

      {step === 3 && result && (
        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Step 3 — 抓取結果</h2>
          <p className="mt-1 text-sm text-gray-500">
            Run ID：{result.run_id}　會議日期：{result.meeting_date}
          </p>
          <table className="mt-6 w-full text-left text-sm">
            <thead className="border-b text-xs uppercase text-gray-500">
              <tr>
                <th className="py-2">欄位</th>
                <th className="py-2">數值</th>
                <th className="py-2">單位</th>
                <th className="py-2">信心</th>
                <th className="py-2">來源</th>
              </tr>
            </thead>
            <tbody>
              {result.slots.map((s) => (
                <tr key={s.slot_key} className="border-b last:border-0">
                  <td className="py-2 font-medium text-gray-900">{s.label}</td>
                  <td className="py-2">{s.value ?? "—"}</td>
                  <td className="py-2 text-gray-500">{s.unit ?? ""}</td>
                  <td className="py-2">
                    <span
                      className={
                        s.confidence === "high"
                          ? "rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700"
                          : s.confidence === "medium"
                            ? "rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-700"
                            : "rounded-full bg-red-50 px-2 py-0.5 text-xs text-red-700"
                      }
                    >
                      {s.confidence}
                    </span>
                  </td>
                  <td className="py-2 text-xs text-gray-500">{s.source ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-8 flex justify-between">
            <button
              onClick={() => setStep(2)}
              className="rounded-lg px-3 py-2 text-sm text-gray-600 ring-1 ring-gray-200 hover:bg-gray-50"
            >
              ← 上一步
            </button>
            <button
              onClick={() => setStep(4)}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              下一步：補內部資料 →
            </button>
          </div>
        </section>
      )}

      {step === 4 && (
        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Step 4 — 補內部資料</h2>
          <p className="mt-1 text-sm text-gray-500">
            這些欄位無法自動抓取，請手動填寫。空白會在 Word 中顯示「—」。
          </p>
          <form
            onSubmit={internalForm.handleSubmit((data) =>
              internalMutation.mutate(data),
            )}
            className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2"
          >
            <label className="block">
              <span className="text-sm font-medium text-gray-700">會議時間</span>
              <input
                {...internalForm.register("meeting_time")}
                placeholder="17:00~17:30"
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-gray-700">
                採購合約剩餘總量（噸）
              </span>
              <input
                {...internalForm.register("contract_remaining_tons")}
                placeholder="57,198"
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-gray-700">可使用至</span>
              <input
                {...internalForm.register("contract_usable_until")}
                placeholder="116 年 1 月"
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="text-sm font-medium text-gray-700">上週會議結論</span>
              <textarea
                {...internalForm.register("meeting_conclusion_last_week")}
                rows={2}
                placeholder="當週鋼筋市場皆維持平盤……"
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </label>
            <label className="block sm:col-span-2">
              <span className="text-sm font-medium text-gray-700">本週會議結論</span>
              <textarea
                {...internalForm.register("meeting_conclusion_this_week")}
                rows={3}
                placeholder="當前國內鋼筋市場正處於……"
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </label>

            <div className="sm:col-span-2 mt-4 flex justify-between">
              <button
                type="button"
                onClick={() => setStep(3)}
                className="rounded-lg px-3 py-2 text-sm text-gray-600 ring-1 ring-gray-200 hover:bg-gray-50"
              >
                ← 上一步
              </button>
              <button
                type="submit"
                disabled={internalMutation.isPending}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
              >
                {internalMutation.isPending
                  ? "更新 Word 中…"
                  : "套用並前往下載 →"}
              </button>
            </div>
            {internalMutation.error && (
              <p className="sm:col-span-2 text-sm text-red-600">
                更新失敗：{(internalMutation.error as Error).message}
              </p>
            )}
          </form>
        </section>
      )}

      {step === 5 && result && (
        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Step 5 — 下載 Word</h2>
          <p className="mt-2 text-sm text-gray-500">
            Run ID：{result.run_id}　產出狀態：
            {result.has_output ? (
              <span className="font-medium text-emerald-700">已就緒</span>
            ) : (
              <span className="font-medium text-amber-700">尚未產生</span>
            )}
          </p>
          <div className="mt-6 flex gap-3">
            <button
              onClick={downloadDocx}
              disabled={!result.has_output}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
            >
              📥 下載會議記錄 Word
            </button>
            <button
              onClick={() => setStep(4)}
              className="rounded-lg px-3 py-2 text-sm text-gray-600 ring-1 ring-gray-200 hover:bg-gray-50"
            >
              ← 修改內部資料
            </button>
          </div>
          <p className="mt-6 text-xs text-gray-400">
            打開 Word 後，紅字代表低信心欄位，灰色「—」代表尚未填入。
          </p>
        </section>
      )}
    </main>
  );
}
