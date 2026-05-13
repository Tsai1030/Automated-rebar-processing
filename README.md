# 鋼筋會議記錄自動填盤系統

每週鋼筋採購會議前，自動從公開來源抓取本週市場盤價，填入會議記錄模板，產出 Word 檔給承辦人 review。

## 文件

- [計畫書 v1](計畫書_v1.md)
- [Stage 0 技術設計 v2](Stage0_技術設計.md)
- [模板來源](1150504會議記錄_整理版.md)

## 架構

```
SEARCH/
├── backend/    FastAPI + LangGraph (Python, uv)        port 8001
├── frontend/   Next.js 14 + Tailwind + shadcn          port 3001
├── docs/       設計文件
└── .env        OpenAI + LangSmith key（不入 git）
```

## 啟動

### 後端
```powershell
cd backend
uv sync
uv run uvicorn src.main:app --reload --port 8001
```

### 前端
```powershell
cd frontend
npm install
npm run dev -- --port 3001
```

開啟 http://localhost:3001
