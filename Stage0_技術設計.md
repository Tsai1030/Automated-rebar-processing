# Stage 0 — 技術設計文件 (v2)

> 版本：v2（架構從 Streamlit 改為 Next.js + FastAPI）
> 日期：2026/05/12
> 對應計畫書：計畫書_v1.md
> Stage 0 目標：建立可擴充骨架，端到端跑通 **1 個來源（豐興 SD280/SD420W）→ Word 輸出**，後續 Stage 只需加 source/slot。

---

## 1. 架構總覽

```
┌──────────────────────────────────────────────┐
│  Browser (員工，區網 PC)                       │
└──────────────────┬───────────────────────────┘
                   │ http://<dev-pc-ip>:3001
                   ▼
┌──────────────────────────────────────────────┐
│  Frontend：Next.js 14 (App Router)             │
│  - TypeScript / Tailwind / shadcn/ui           │
│  - TanStack Query / react-hook-form / zod      │
│  - 處理 JWT cookie、表單、預覽                  │
└──────────────────┬───────────────────────────┘
                   │ fetch  /api/*  (REST JSON, credentials: include)
                   ▼
┌──────────────────────────────────────────────┐
│  Backend：FastAPI (Python, uv)                 │
│  - /auth/*：簽發/驗證 JWT、set HttpOnly cookie │
│  - /generation/*：抓取、產 Word                │
│  - /history/*：歷史查詢                        │
│                                                │
│  ├─ core/         主流程編排                   │
│  ├─ sources/      Scraper（豐興/中鋼/...）     │
│  ├─ llm/          OpenAI 包裝                  │
│  ├─ output/       python-docx renderer        │
│  ├─ storage/      SQLite + WAL                │
│  ├─ validator/    驗證規則                     │
│  └─ narrator/     段落敘述生成（template）     │
└──────────────────────────────────────────────┘
```

---

## 2. 專案結構

頂層 monorepo（兩個獨立子專案）：

```
SEARCH/
├── backend/                    ← FastAPI (Python + uv)
│   ├── pyproject.toml
│   ├── .env.example
│   ├── .env                    ← gitignore
│   ├── src/
│   │   ├── main.py             ← FastAPI 入口
│   │   ├── config.py
│   │   ├── api/                ← 路由層
│   │   │   ├── auth.py
│   │   │   ├── generation.py
│   │   │   ├── history.py
│   │   │   └── dependencies.py ← JWT、rate limit
│   │   ├── core/
│   │   │   ├── slot_schema.py
│   │   │   ├── orchestrator.py
│   │   │   └── pipeline.py
│   │   ├── sources/
│   │   │   ├── base.py
│   │   │   └── fengxing.py
│   │   ├── llm/
│   │   │   ├── base.py
│   │   │   └── openai_client.py
│   │   ├── storage/
│   │   │   ├── base.py
│   │   │   └── sqlite_store.py
│   │   ├── validator/
│   │   ├── narrator/
│   │   ├── output/
│   │   │   ├── base.py
│   │   │   └── docx_renderer.py
│   │   └── auth/
│   │       ├── jwt_handler.py
│   │       ├── password.py
│   │       └── rate_limit.py
│   ├── templates/
│   │   ├── meeting_template.docx
│   │   └── slot_mapping.json
│   ├── data/
│   │   ├── app.db
│   │   └── outputs/
│   └── tests/
│
├── frontend/                   ← Next.js (TS + Tailwind)
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── next.config.mjs
│   ├── .env.local              ← gitignore
│   ├── src/
│   │   ├── app/                ← App Router
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx        ← 首頁（重導）
│   │   │   ├── login/
│   │   │   ├── generate/
│   │   │   │   ├── page.tsx    ← 5-Step 主流程
│   │   │   │   └── components/
│   │   │   └── history/
│   │   ├── components/
│   │   │   └── ui/             ← shadcn 元件
│   │   ├── lib/
│   │   │   ├── api.ts          ← fetch wrapper
│   │   │   ├── auth.ts         ← session helper
│   │   │   └── types.ts        ← 與後端 Pydantic 對齊的 types
│   │   └── hooks/
│   └── public/
│
├── docs/
│   ├── 計畫書_v1.md
│   ├── Stage0_技術設計.md
│   └── api_contract.md
│
├── .gitignore
└── README.md
```

**為什麼分兩個子專案而非 Next.js API routes？**
業務核心（python-docx、爬蟲）在 Python 比 Node 強很多，把它們塞進 Next.js API route 沒有意義（還要跨 process call Python，更亂）。前後分離反而清楚。

---

## 3. 後端設計

### 3.1 初始化
```powershell
cd backend
uv init --name steel-backend
uv add fastapi uvicorn[standard] httpx beautifulsoup4 lxml `
       pydantic pydantic-settings sqlmodel `
       python-docx openai python-jose[cryptography] `
       passlib[bcrypt] slowapi python-dotenv tenacity
uv add --dev pytest pytest-asyncio mypy ruff respx httpx
```

### 3.2 FastAPI 啟動
```python
# src/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address

from .api import auth, generation, history
from .config import settings
from .storage.sqlite_store import init_db

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Steel Meeting Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],  # http://localhost:3001 或區網 IP
    allow_credentials=True,                     # 關鍵：讓 cookie 過得來
    allow_methods=["*"],
    allow_headers=["*"],
)
app.state.limiter = limiter

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(generation.router, prefix="/api/generation", tags=["generation"])
app.include_router(history.router, prefix="/api/history", tags=["history"])

@app.on_event("startup")
def on_startup():
    init_db(settings.DB_PATH)
```

### 3.3 JWT + HttpOnly Cookie
```python
# src/api/auth.py
from fastapi import APIRouter, Response, Depends, HTTPException
from datetime import timedelta

router = APIRouter()

@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, body: LoginRequest, response: Response):
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")

    access_token = create_token(user.id, timedelta(minutes=30))
    refresh_token = create_token(user.id, timedelta(days=7), refresh=True)

    response.set_cookie(
        key="access_token", value=access_token,
        httponly=True, secure=settings.COOKIE_SECURE,  # MVP=False
        samesite="lax", max_age=30*60, path="/",
    )
    response.set_cookie(
        key="refresh_token", value=refresh_token,
        httponly=True, secure=settings.COOKIE_SECURE,
        samesite="lax", max_age=7*24*60*60, path="/api/auth",
    )
    return {"user": {"id": user.id, "username": user.username}}

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/auth")
    return {"ok": True}

@router.get("/me")
def me(user = Depends(get_current_user)):
    return user
```

### 3.4 受保護端點
```python
# src/api/generation.py
@router.post("/run")
@limiter.limit("10/hour")
def run_generation(
    request: Request,
    body: GenerationRequest,
    user = Depends(get_current_user),
):
    run_id = orchestrator.start(meeting_date=body.meeting_date, user=user.username)
    return {"run_id": run_id, "status": "running"}

@router.get("/{run_id}")
def get_run(run_id: int, user = Depends(get_current_user)):
    return orchestrator.get_status(run_id)

@router.post("/{run_id}/internal-data")
def fill_internal(run_id: int, data: InternalDataDto, user = Depends(get_current_user)):
    orchestrator.merge_internal(run_id, data)
    return {"ok": True}

@router.get("/{run_id}/docx")
def download_docx(run_id: int, user = Depends(get_current_user)):
    path = orchestrator.render_docx(run_id)
    return FileResponse(path, filename=f"會議記錄_{run_id}.docx")
```

### 3.5 抽象介面（同 v1，保留）
- `SourceAdapter` — `provides: list[str]`、`async fetch(date) -> list[FetchResult]`
- `HistoryStore` — `upsert_price`、`get_latest_before`
- `DocumentRenderer` — `render(values, output_path)`
- `LLMClient` — `chat(messages)`、`web_search(query)`

### 3.6 SQLite WAL 啟動
```python
# src/storage/sqlite_store.py
from sqlmodel import create_engine

def init_db(path: str) -> Engine:
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.exec_driver_sql("PRAGMA busy_timeout=5000")
    SQLModel.metadata.create_all(engine)
    return engine
```

### 3.7 SQLite Schema（同 v1）
保留 v1 的四張表：`users`、`price_history`、`generation_runs`、`rate_limit_log`。

> Rate limit 用 slowapi 本身在記憶體就夠了，`rate_limit_log` 表改為「成本控制」用途（記 OpenAI 呼叫次數）。

### 3.8 Slot Schema
保留 v1 的設計，但用 Pydantic v2，並用 `datamodel-code-generator` 或自寫 export script 產出 TypeScript types 給前端用。

---

## 4. 前端設計

### 4.1 初始化
```powershell
cd frontend
npx create-next-app@latest . --typescript --tailwind --app --src-dir --import-alias "@/*"
npx shadcn@latest init
npx shadcn@latest add button input form card table progress toast dialog calendar
npm install @tanstack/react-query react-hook-form zod @hookform/resolvers
```

### 4.2 fetch wrapper（credentials: include）
```typescript
// src/lib/api.ts
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",  // 關鍵：cookie 才會跟著走
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    if (res.status === 401) window.location.href = "/login";
    throw new Error(await res.text());
  }
  return res.json() as Promise<T>;
}
```

### 4.3 受保護路由（middleware）
```typescript
// src/middleware.ts
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const token = req.cookies.get("access_token");
  const isAuthPage = req.nextUrl.pathname.startsWith("/login");

  if (!token && !isAuthPage) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  if (token && isAuthPage) {
    return NextResponse.redirect(new URL("/generate", req.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

### 4.4 5-Step 主頁面（雛形）
```tsx
// src/app/generate/page.tsx
"use client";
export default function GeneratePage() {
  const [step, setStep] = useState<1|2|3|4|5>(1);
  return (
    <div className="container mx-auto py-8 max-w-4xl">
      <Stepper current={step} steps={["設定", "抓取", "補內部", "預覽", "下載"]} />
      {step === 1 && <Step1Setup onNext={() => setStep(2)} />}
      {step === 2 && <Step2Fetch onNext={() => setStep(3)} />}
      {step === 3 && <Step3InternalForm onNext={() => setStep(4)} />}
      {step === 4 && <Step4Preview onNext={() => setStep(5)} />}
      {step === 5 && <Step5Download />}
    </div>
  );
}
```

### 4.5 表單驗證（zod，與後端 Pydantic 對齊）
```typescript
// src/lib/schemas.ts
import { z } from "zod";

export const internalDataSchema = z.object({
  contract_remaining_tons: z.number().int().nonnegative(),
  contract_usable_until: z.string().regex(/^\d{3}\/\d{1,2}$/),  // 例：116/1
  work_orders_count: z.number().int().positive(),
  // ... 其餘 C 類欄位
});
export type InternalData = z.infer<typeof internalDataSchema>;
```

### 4.6 TypeScript types 與後端對齊
建一個 build script：後端啟動時把 slot_schema 與 DTO 匯出成 JSON Schema → 前端 `npm run sync-types` 用 `json-schema-to-typescript` 產生 `src/lib/types.gen.ts`。避免手動同步漂移。

---

## 5. API 合約（Stage 0 範圍）

| Method | Path | Body / Query | Response | 限流 |
|---|---|---|---|---|
| POST | `/api/auth/login` | `{username, password}` | `{user}` + Set-Cookie | 5/min |
| POST | `/api/auth/logout` | — | `{ok}` | — |
| GET | `/api/auth/me` | — | `{user}` | — |
| POST | `/api/auth/refresh` | — (refresh cookie) | `{ok}` + 新 access cookie | 10/min |
| POST | `/api/generation/run` | `{meeting_date, fengxing_date}` | `{run_id, status}` | 10/hour |
| GET | `/api/generation/{run_id}` | — | `{status, slots, confidence_map}` | — |
| POST | `/api/generation/{run_id}/internal-data` | `InternalData` | `{ok}` | — |
| GET | `/api/generation/{run_id}/preview` | — | `{markdown_preview}` | — |
| GET | `/api/generation/{run_id}/docx` | — | `.docx` file stream | 20/hour |
| GET | `/api/history/runs` | `?limit=20` | `[{run_id, meeting_date, ...}]` | — |

詳細 schema 寫在 `docs/api_contract.md`（由 FastAPI 自動產出 OpenAPI 3.1 spec，前端直接 import）。

---

## 6. Stage 0 範圍（端到端可跑通）

**只做這 5 個 slot**，但要把所有架構打通：

| key | 來源 | 處理 |
|---|---|---|
| `meeting_date` | 使用者輸入 | 直接寫入 |
| `fx_sd280_price` | 豐興 scraper | 抓 → DB → 寫 docx |
| `fx_sd280_delta` | 系統自算 | 本週 - DB 上週 |
| `fx_sd420w_price` | 豐興 scraper | 同上 |
| `fx_sd420w_delta` | 系統自算 | 同上 |
| `contract_remaining_tons` | 員工填 | 表單寫入 |

第一次跑沒有上週值 → delta 顯示「—」。

---

## 7. 完成驗收標準

1. ✅ `uv run uvicorn src.main:app --reload --port 8001` 啟後端
2. ✅ `npm run dev` 啟前端 (port 3001)
3. ✅ `/api/docs` 看得到 Swagger UI
4. ✅ 註冊一個使用者 (或 admin seed script)
5. ✅ 瀏覽器訪問 `http://localhost:3001` → 重導 `/login`
6. ✅ 登入成功 → cookie 帶上 → 進入 `/generate`
7. ✅ 設定日期 2026/5/4 → 按抓取 → 進度條顯示 → 出現結果表
8. ✅ 填合約剩餘 → 預覽顯示完整 markdown → 下載 Word
9. ✅ Word 中表格與段落數值都正確、低信心欄位紅字
10. ✅ Rate limit 生效（連 11 次抓取被擋）
11. ✅ `app.db-wal` 檔案存在（驗證 WAL）
12. ✅ `mypy --strict backend/src/` 通過、`ruff check` 通過
13. ✅ `tsc --noEmit` 通過、`next lint` 通過

---

## 8. 待驗證 / 待決定

| # | 項目 | 何時要解 |
|---|---|---|
| 1 | 豐興官網實際 URL 與 HTML 結構 | 開工前要看一次網頁 |
| 2 | Word 模板實際做法 | Stage 0 第一週做出 v1 |
| 3 | TS types 與 Pydantic 同步機制 | Stage 0 中段建立 |
| 4 | 區網部署時的 CORS / cookie SameSite 行為驗證 | Stage 0 收尾 |
| 5 | OpenAI 模型選擇 | Stage 1 才決 |

---

## 9. 預估工期（Stage 0，重新估算）

| 任務 | 工時 |
|---|---|
| Monorepo + 兩專案初始化（uv + Next.js） | 3h |
| FastAPI 基礎骨架 + CORS + .env | 3h |
| SQLite schema + WAL + migrations | 3h |
| 抽象介面與 slot_schema (含 TS 同步) | 5h |
| JWT + 登入 + cookie 端點 | 5h |
| Rate limit + 受保護路由 | 3h |
| 豐興 scraper（含網頁分析） | 6h |
| Word 模板製作 + python-docx 寫入 | 6h |
| Next.js 專案 + shadcn 設定 + middleware auth | 4h |
| 5-Step 主頁面 UI | 10h |
| 登入頁 + 歷史頁 | 4h |
| TanStack Query + 整合 API | 4h |
| 端到端整合測試 | 5h |
| 文件 + README + 啟動 script | 3h |
| **合計** | **64h ≈ 8 個工作天** |

比 Streamlit 版多 ~2 天（多在前端 UI 與 TS-Pydantic 同步），但換來：
- 真正可給多人用的 web 應用
- JWT cookie auth 不需要 workaround
- 後續加功能不用大改架構

---

## 10. 下一步

1. ⬜ 你 review 這份 v2 設計
2. ⬜ 確認 Node.js 版本（建議 20 LTS）、npm/pnpm 偏好
3. ⬜ 提供豐興官網 URL（或我去找）
4. ⬜ 確認 OpenAI key 已備
5. ⬜ 我建立 monorepo 骨架（backend + frontend 兩個空專案）→ 你檢視
6. ⬜ 開始實作（按 §9 順序）
