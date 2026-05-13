"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { CscSaveRequest, CscSnapshot, UserResponse } from "@/lib/types";

type Group = "monthly" | "quarterly";

const GROUP_LABELS: Record<Group, string> = {
  monthly: "八.1 月盤鋼品",
  quarterly: "八.2 季盤鋼品",
};

interface EditableRow {
  slot_index: number;
  product_name: string;
  prev_price: string;       // string while editing
  change_amount: string;
}

function snapToEditable(snap: CscSnapshot): EditableRow[] {
  return snap.rows.map((r) => ({
    slot_index: r.slot_index,
    product_name: r.product_name,
    prev_price: String(r.prev_price),
    change_amount: String(r.change_amount),
  }));
}

function GroupEditor({ group }: { group: Group }) {
  const qc = useQueryClient();
  const queryKey = ["csc", group];
  const { data, isLoading } = useQuery<CscSnapshot>({
    queryKey,
    queryFn: () => api<CscSnapshot>(`/api/admin/csc/${group}`),
  });

  const [period, setPeriod] = useState("");
  const [announceDate, setAnnounceDate] = useState("");
  const [rows, setRows] = useState<EditableRow[]>([]);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setPeriod(data.period_label);
      setAnnounceDate(data.announce_date);
      setRows(snapToEditable(data));
    }
  }, [data]);

  const save = useMutation({
    mutationFn: (body: CscSaveRequest) =>
      api(`/api/admin/csc/${group}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setSavedMsg("已儲存");
      qc.invalidateQueries({ queryKey });
      setTimeout(() => setSavedMsg(null), 3000);
    },
  });

  const update = (idx: number, field: "prev_price" | "change_amount", v: string) => {
    setRows((prev) =>
      prev.map((r, i) =>
        i === idx ? { ...r, [field]: v.replace(/[^\d.+\-,]/g, "") } : r,
      ),
    );
  };

  const onSave = () => {
    const body: CscSaveRequest = {
      period_label: period,
      announce_date: announceDate,
      rows: rows.map((r) => ({
        slot_index: r.slot_index,
        prev_price: parseInt(r.prev_price.replace(/,/g, ""), 10) || 0,
        change_amount: parseInt(r.change_amount.replace(/[,+]/g, ""), 10) || 0,
      })),
    };
    save.mutate(body);
  };

  if (isLoading) return <div className="text-sm text-gray-500">載入中…</div>;

  return (
    <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
      <h2 className="text-lg font-semibold text-gray-900">{GROUP_LABELS[group]}</h2>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-gray-700">期別</span>
          <input
            type="text"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            placeholder={group === "monthly" ? "115 年 5 月份" : "115 年第二季"}
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-gray-700">中鋼發佈日期</span>
          <input
            type="text"
            value={announceDate}
            onChange={(e) => setAnnounceDate(e.target.value)}
            placeholder="2026/4/15"
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm"
          />
        </label>
      </div>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b text-xs uppercase text-gray-500">
            <tr>
              <th className="py-2 text-left">產品</th>
              <th className="py-2 text-right">{group === "monthly" ? "上月基價" : "上季基價"}</th>
              <th className="py-2 text-right">調整金額</th>
              <th className="py-2 text-right">調整後基價 (自動)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const prev = parseInt(r.prev_price.replace(/,/g, ""), 10) || 0;
              const change = parseInt(r.change_amount.replace(/[,+]/g, ""), 10) || 0;
              return (
                <tr key={r.slot_index} className="border-b last:border-0">
                  <td className="py-2 pr-3 text-gray-900">{r.product_name}</td>
                  <td className="py-2">
                    <input
                      type="text"
                      value={r.prev_price}
                      onChange={(e) => update(i, "prev_price", e.target.value)}
                      className="w-24 rounded-md border border-gray-300 px-2 py-1 text-right text-sm shadow-sm"
                    />
                  </td>
                  <td className="py-2">
                    <input
                      type="text"
                      value={r.change_amount}
                      onChange={(e) => update(i, "change_amount", e.target.value)}
                      className="w-20 rounded-md border border-gray-300 px-2 py-1 text-right text-sm text-red-600 shadow-sm"
                    />
                  </td>
                  <td className="py-2 pr-3 text-right text-gray-700">
                    {(prev + change).toLocaleString()}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          onClick={onSave}
          disabled={save.isPending}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
        >
          {save.isPending ? "儲存中…" : "💾 儲存"}
        </button>
        {savedMsg && (
          <span className="text-sm text-emerald-700">{savedMsg}</span>
        )}
        {save.error && (
          <span className="text-sm text-red-600">
            錯誤：{(save.error as Error).message}
          </span>
        )}
      </div>
    </section>
  );
}

export default function CscAdminPage() {
  const router = useRouter();
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<UserResponse>("/api/auth/me"),
  });

  return (
    <main className="mx-auto w-full max-w-6xl px-6 py-10">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900">
            中鋼盤價管理
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            每月/每季由中鋼通知後在此更新。儲存後，下次生成 Word 時 八.1 / 八.2 自動填入。
            登入：{me?.username ?? "…"}
          </p>
        </div>
        <button
          onClick={() => router.push("/generate")}
          className="rounded-lg px-3 py-1.5 text-sm text-gray-600 ring-1 ring-gray-200 hover:bg-gray-100"
        >
          ← 回主流程
        </button>
      </header>

      <div className="space-y-8">
        <GroupEditor group="monthly" />
        <GroupEditor group="quarterly" />
      </div>
    </main>
  );
}
