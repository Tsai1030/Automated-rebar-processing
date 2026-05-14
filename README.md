# 鋼筋會議記錄自動填盤系統

每週鋼筋採購會議前，自動從公開來源抓取本週市場盤價、產生敘述段落、填入 Word 模板，產出會議記錄草稿給承辦人 review。

線上部署：Render free + Neon Postgres free（雙 0 元方案）
GitHub：<https://github.com/Tsai1030/Automated-rebar-processing>

---

## 1. 為什麼做這個

承辦人原本每週手動查 10+ 個盤價來源（豐興鋼鐵、中鋼、LME、西本新幹線、國際廢鋼），整理成會議記錄。流程耗時且容易抄錯。本系統把可自動化的部分（公開資料 + 敘述段落）交給程式，**內部資料（合約剩餘量、會議結論等）仍由人填寫**，避免 LLM 幻覺造成決策偏誤。

最終產出物：一份 `.docx` 檔，承辦人**校稿後直接送出**，不是當作 source of truth。

---

## 2. 系統架構總覽

```
┌─────────────────────────────────────────────────────────────────┐
│                          瀏覽器                                  │
│  (Next.js 16 App Router, Tailwind, TanStack Query, MacShell)    │
└──────────────────────┬──────────────────────────────────────────┘
                       │ 同源 /api/* (HttpOnly cookie)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│   Frontend Web Service (Render free, Node)                      │
│   • next start                                                  │
│   • proxy.ts → 未登入 redirect 到 /login (排除 /api/*)          │
│   • next.config.ts rewrites /api/:path*                         │
│     → API_PROXY_TARGET/api/:path*                               │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP (內部呼叫，不經過瀏覽器)
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│   Backend Web Service (Render free, Python 3.12 + uv)           │
│   FastAPI + LangGraph + asyncio background tasks                │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│   │  /auth   │  │ /admin   │  │/generation│                     │
│   │ JWT 簽發 │  │ user CRUD│  │ 抓取流程  │                      │
│   │HttpOnly  │  │ usage    │  │ 背景任務  │                      │
│   └──────────┘  └──────────┘  └──────────┘                      │
└────┬────────────────────────────────────────────┬───────────────┘
     │ SQLAlchemy + psycopg3                      │ httpx + LangGraph
     ▼                                             ▼
┌──────────────────────┐               ┌───────────────────────────┐
│ Neon Postgres free   │               │ 外部資料來源              │
│ • users              │               │ • steelnet.com.tw 會員區  │
│ • generation_runs    │               │   (豐興開盤新聞)          │
│ • price_history      │               │ • OpenAI web_search       │
│ • csc_price_state    │               │   (西本新幹線、LME)       │
│ • csc_announcement_  │               │ • OpenAI ChatCompletion   │
│   meta               │               │   (撰寫敘述段落)          │
└──────────────────────┘               │ • LangSmith trace upload  │
                                       └───────────────────────────┘
```

---

## 3. 技術選型

| 層次 | 工具 | 選擇理由 |
|---|---|---|
| 前端框架 | Next.js 16 + App Router + TypeScript | App Router 內建 SSR + 同源代理（rewrites）省去 CORS；TS 嚴格型別降低跟後端 schema drift |
| 樣式 | Tailwind v4 + 自製 macOS 風格 MacShell | 業界標準 utility-first；自製 shell 統一視覺 |
| 表單 / 資料 | react-hook-form + zod + TanStack Query | 表單驗證、伺服器狀態快取、樂觀更新一次到位 |
| 後端框架 | FastAPI + uvicorn | 原生 async、自動 OpenAPI、依賴注入適合中型 API |
| 工作流 | LangGraph | scraper → validator → narrator → renderer 的有狀態多步驟流程；附 retry/branching |
| LLM SDK | OpenAI Python SDK + LangChain | `gpt-5.4-mini`（user-pinned），web_search 抓即時資訊 |
| 資料庫 | 本機 SQLite + WAL，雲端 Neon Postgres | dev 零設定；prod 用免費 Postgres 永久存放 |
| 認證 | JWT + HttpOnly Cookie | 不存 token 在 JS、配合同源代理就免 CORS |
| Rate limit | slowapi（in-memory）| 對單機部署夠用 |
| Word 輸出 | python-docx | 模板用 `{{slot_key}}` placeholder，runtime 替換 |
| 套件管理 | uv（backend）+ npm（frontend）| uv 解析快、lockfile 確定性 |
| 部署 | Render Web Service ×2 + Neon | 免費永久可用、auto-deploy on git push |
| 觀測 | LangSmith | LangGraph 內建 trace，方便看每步 LLM 呼叫 |

---

## 4. LangGraph 工作流

主要流程在 `backend/src/steel_backend/core/orchestrator.py`：

```
              ┌─────────┐
   inputs ───▶│  fetch  │  並行呼叫每個 SourceAdapter
              └────┬────┘
                   ▼
              ┌──────────┐
              │ validate │  檢查必填欄位、合理範圍
              └────┬─────┘
                   ▼
              ┌──────────┐
              │ persist  │  寫入 price_history (key=opening Monday)
              └────┬─────┘
                   ▼
              ┌──────────┐
              │ narrate  │  填 slot_values dict、寫敘述段落 (LLM)
              └────┬─────┘   讀 price_history 過去 8 週、讀中鋼 admin
                   ▼
              ┌──────────┐
              │  render  │  python-docx 寫入 Word 模板
              └────┬─────┘
                   ▼
              output_path
```

**Slot schema** 是單一真實來源（`core/slot_schema.py`），加新欄位的流程：

1. 在 `SLOTS` 加一個 `SlotDef`
2. 若需自動抓取：建一個 `SourceAdapter` 子類別、`provides` 包含這個 key
3. orchestrator / validator / renderer / 前端都從 schema 讀，自動同步

**Source adapters**（`sources/`）：
- `fengxing.py` / `fengxing_finder.py` — 從 steelnet 抓豐興開盤新聞 + LLM 篩選 + 解析
- `steelnet_client.py` — 共用 session 處理 steelnet 會員 login
- `weekly_market.py` — 國際廢鋼數字
- `market_narrator.py` — OpenAI web_search + 撰寫 六.3/六.4/九.1/九.2 段落

---

## 5. 資料模型

定義在 `backend/src/steel_backend/storage/models.py`（SQLModel）。

| Table | 用途 | 關鍵欄位 |
|---|---|---|
| `users` | 系統帳號 | `username` UK、`password_hash`（bcrypt）、`role`（admin/user）、`is_active`、`last_login` |
| `generation_runs` | 每次抓取的紀錄 | `meeting_date`、`status`（running/success/partial/failed）、`output_path`、`result_json`（slot_values + confidence + fetched 序列化）、`started_by` |
| `price_history` | 8 週歷史盤價 | `slot_key + value_date + source` 三元組 unique；用來填 七.近期盤價 |
| `csc_price_state` | 中鋼盤價（月盤 10 列、季盤 16 列）| `group + slot_index`；由 admin 表單覆寫 |
| `csc_announcement_meta` | 中鋼公告 metadata | `period_label`、`announce_date` |

**Migration 策略**：不用 Alembic。`storage/sqlite_store.py#_apply_lightweight_migrations` 在啟動時用 `PRAGMA table_info` (SQLite) 或 `ADD COLUMN IF NOT EXISTS` (Postgres) 補欄位。只支援 additive 變更——足夠單人專案。

---

## 6. API 設計

所有 API 都在 `/api` prefix 下，需要 cookie 認證（除了 `/api/health`）。

### Auth (`/api/auth`)
| Method | Path | 用途 |
|---|---|---|
| POST | `/login` | username + password → 設 HttpOnly access + refresh cookie |
| POST | `/logout` | 清 cookie |
| GET | `/me` | 回傳目前 user info |
| POST | `/refresh` | 用 refresh token 換新 access token |

### Generation (`/api/generation`)
| Method | Path | 用途 |
|---|---|---|
| POST | `/run` | 開新 run，**立即回 run_id**，背景跑 LangGraph |
| POST | `/{id}/internal-data` | 補內部資料後重跑 narrate + render |
| GET | `/{id}` | 輪詢 run 狀態；status=success 時帶回完整 slots |
| GET | `/{id}/docx` | 下載產出的 Word 檔 |

**背景任務模式**：Render free 對單一 HTTP request 約 100 秒就會切連線，但 LangGraph 跑完要 150–200 秒。所以：
- POST `/run` 建 row 後 `asyncio.create_task` 啟動背景任務，立刻回 `status="running"`
- 前端每 2.5 秒輪詢 `GET /{id}`
- 背景任務完成時把結果寫進 `generation_runs.result_json`、status 變 success/failed
- 輪詢拿到非 running 狀態 → loading overlay 結束、跳下一步

啟動時 `main.py#_reap_stranded_runs` 會把任何 status=running 的 row 改成 failed（防止 deploy 中斷後 row 卡死）。

### Admin (`/api/admin`)
| Method | Path | 用途 |
|---|---|---|
| GET | `/users` | 列出所有帳號（admin only）|
| POST | `/users` | 建立新帳號 |
| PATCH | `/users/{id}` | 改 role / is_active |
| POST | `/users/{id}/password` | 重設密碼 |
| DELETE | `/users/{id}` | 刪除（不能刪自己）|
| GET | `/usage` | 各帳號的執行統計（總次數、成功/失敗、最後執行時間）|
| GET / PUT | `/csc/{group}` | 中鋼月盤 / 季盤的讀寫 |

---

## 7. 認證與帳號管理

**設計原則：邀請制，沒有自助註冊**。

- **建第一個 admin**：本機跑 `uv run python scripts/create_user.py --username admin --role admin`，互動式輸入 bcrypt 密碼
- **之後建/停/刪帳號**：登入後從 sidebar「帳號管理」操作，呼叫 `/api/admin/users` API
- **角色**：`admin` 看得到「帳號管理」「使用流量」兩個 admin sidebar；`user` 只能用「產生會議記錄」「中鋼盤價管理」
- **停用**：`users.is_active=false` 後登入直接被 401，不會看到任何頁面
- **自保**：admin 不能 demote / 停用 / 刪除自己

**JWT 內容**：`{sub: user_id, username, role, type: access|refresh, exp, iat}`。HttpOnly cookie + SameSite=lax + Secure（prod）+ JS 讀不到。token 過期前 30 分鐘自動 refresh。

---

## 8. 雲端部署（Render + Neon）

### 8.1 服務拓樸

```
┌───────────────────────────┐         ┌───────────────────────────┐
│ steel-frontend            │         │ steel-backend             │
│ Render Web Service (free) │         │ Render Web Service (free) │
│ Node 20, Next.js 16       │ ──────▶ │ Python 3.12, uvicorn      │
│ next start                │         │ uv run uvicorn ...        │
│ next.config rewrites      │         │ asyncio background tasks  │
└─────────────┬─────────────┘         └─────────────┬─────────────┘
              │                                     │
              │ 瀏覽器只看到 frontend origin        │ psycopg3 + SSL
              │                                     ▼
              │                       ┌────────────────────────────┐
              │                       │ Neon Postgres free         │
              │                       │ ap-southeast-1 (Singapore) │
              │                       │ 3 GB 永久免費              │
              │                       └────────────────────────────┘
              ▼
        終端使用者
```

藍圖：根目錄 `render.yaml`，新增 service 時直接 `Apply Blueprint` 一次到位。

### 8.2 同源代理（關鍵設計）

`*.onrender.com` 在 PSL 上 → frontend `*-frontend.onrender.com` 與 backend `*-backend.onrender.com` 被瀏覽器視為**不同 site**，跨站 cookie 即使 `SameSite=None; Secure` 也常被 Chrome 擋掉。

解法：讓 frontend 的 Node server 代理 `/api/*` 到 backend：

```
瀏覽器 ──同源──▶ steel-frontend.onrender.com/api/auth/login
                           │ next.config.ts rewrites
                           ▼
              API_PROXY_TARGET = steel-backend.onrender.com/api/auth/login
```

- `NEXT_PUBLIC_API_BASE = ""` → `lib/api.ts` 用相對路徑 `/api/...`
- `API_PROXY_TARGET = <backend URL>` → server-side 代理
- Cookie 永遠以 frontend 域為主，全程同源，瀏覽器照常送出
- `proxy.ts` (Next 16 改名的 middleware) matcher 必須排除 `api`，否則未登入 POST `/api/auth/login` 會被 redirect 到 `/login` 結果 405

### 8.3 環境變數

#### `steel-backend`
| Key | 必填 | 說明 |
|---|---|---|
| `DATABASE_URL` | ✅ | Neon pool 連線字串（`postgresql://...?sslmode=require`）|
| `JWT_SECRET_KEY` | ✅ | 32+ 字元 hex；Render 用 `generateValue: true` 自動產 |
| `COOKIE_SECURE` | ✅ | `true`（必須 HTTPS）|
| `COOKIE_SAMESITE` | ✅ | `lax`（同源代理已搞定跨站問題）|
| `FRONTEND_ORIGIN` | ✅ | frontend 的 onrender URL（給 CORS 用，保險）|
| `OPENAI_API_KEY` | ✅ | OpenAI 帳號 |
| `OPENAI_MODEL` | 預設 `gpt-5.4-mini` | LangGraph LLM model id |
| `STEELNET_USER` / `STEELNET_PASSWORD` | ✅ | steelnet 會員帳密 |
| `LANGCHAIN_TRACING_V2` | 選填 | `true` 啟用 LangSmith trace |
| `LANGCHAIN_API_KEY` | 選填 | LangSmith API key |
| `LANGCHAIN_PROJECT` | 選填 | LangSmith UI 上的專案名 |

#### `steel-frontend`
| Key | 必填 | 說明 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | ✅ 設成空字串 | build-time 嵌入 bundle，空字串讓 `api.ts` 走相對 URL |
| `API_PROXY_TARGET` | ✅ | server-only，rewrites 的目標 = backend URL |

### 8.4 已知 free tier 限制

| 限制 | 影響 | 對應 |
|---|---|---|
| Render 閒置 15 min spin-down | 第一次喚醒 30–60 s | 抓取前先打 `/api/health` 暖機 |
| Neon 閒置 5 min compute 暫停 | 連線首次延遲 +2 s | engine 已設 `pool_pre_ping=True` 自動處理死連線 |
| 單一 HTTP request ~100 s timeout | 阻塞式長請求被切 | 已改背景任務 + 輪詢 |
| Filesystem 暫態 | 產出的 `.docx` 在 spin-down 後消失 | 抓完盡快下載；之後可以把檔案 base64 存進 DB |
| 512 MB RAM / 0.1 CPU | LangGraph 高峰可能慢 | 目前還沒撞到 OOM；如撞到再評估升級 |

---

## 9. 開發指南

### 9.1 本機啟動

需要 Python 3.12+ 與 Node 20+，以及 [uv](https://docs.astral.sh/uv/)。

```powershell
# Backend
cd backend
uv sync
uv run uvicorn steel_backend.main:app --reload --port 8001 --host 0.0.0.0

# Frontend (另一個 terminal)
cd frontend
npm install
npm run dev    # 監聽 3001
```

開 <http://localhost:3001>。本機 DB 預設用 SQLite `backend/data/app.db`（首次啟動會自動建檔 + 跑 migration）。

`.env` 放在專案根目錄（不入 git）：
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5.4-mini
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls-...
JWT_SECRET_KEY=隨機32字元
STEELNET_USER=...
STEELNET_PASSWORD=...
```

### 9.2 建第一個 admin
```powershell
cd backend
uv run python scripts/create_user.py --username admin --role admin
```

### 9.3 灌歷史資料
```powershell
uv run python scripts/seed_csc.py        # 中鋼盤價
uv run python scripts/seed_history.py    # 八週價格歷史
```

### 9.4 跑工作流的單獨 smoke test（不開 server）
```powershell
uv run python scripts/smoke_orchestrator.py 2026-05-12
```

---

## 10. 部署指南

1. push 上 GitHub → Render 自動觸發 build（兩個 service 共用同一 repo）
2. 第一次部署：Render Dashboard → New → Blueprint → 選 repo → Apply（讀 `render.yaml`）
3. 補 secrets：`steel-backend` 的 `OPENAI_API_KEY` / `STEELNET_*` / `DATABASE_URL`、`steel-frontend` 的 `API_PROXY_TARGET`
4. 各自 **Manual Deploy → Clear build cache & deploy**（前端必須清，因為 `NEXT_PUBLIC_*` 是 build-time 嵌入）
5. 本機指向 Neon 跑一次 `create_user.py` + `seed_csc.py` + `seed_history.py` 灌種子資料

---

## 11. 操作流程（使用者視角）

1. **登入** — 用 admin 發給的帳號
2. **產生會議記錄**（Step 1–5）：
   - 設定會議日期（系統自動推算對應週一為盤價基準日）
   - 開始抓取 → 等 2–3 分鐘（loading overlay 顯示 18 個進度步驟）
   - 檢視自動抓到的 slots（低信心欄位會在 Word 內標紅字）
   - 補內部資料（會議時間、合約剩餘量、會議結論）
   - 下載 Word
3. **中鋼盤價管理** — 每月/每季中鋼公告後手動更新
4. **帳號管理 / 使用流量**（admin only）— 加新帳號、看誰跑過幾次

---

## 12. 既有文件

- [計畫書 v1](計畫書_v1.md) — 原始需求與範圍
- [Stage 0 技術設計](Stage0_技術設計.md) — 初版架構決策
- [模板來源](1150504會議記錄_整理版.md) — 5/4 範本

---

## 13. 已知 TODO / 未來方向

- **產出 Word 落地**：目前寫到本地 ephemeral filesystem，spin-down 就消失。可改成 base64 存 DB 或上 R2/S3
- **任務佇列**：若日後使用者變多，asyncio 單程式內背景任務不夠用，應改 Celery / Arq + Redis
- **自動排程**：每週日晚上預跑下週的抓取，週一一早 review 即可
- **多公司模板**：目前模板硬寫，加 multi-tenant 後可上線到其他用戶
- **歷史 / 監控**：把 LangSmith trace 帶回前端，admin 可以看每個 run 內部詳情
