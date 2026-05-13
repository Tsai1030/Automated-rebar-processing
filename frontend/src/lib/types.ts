/**
 * Types mirroring backend Pydantic DTOs.
 *
 * TODO: auto-generate from backend OpenAPI spec (script: scripts/sync-types.ts)
 * to prevent drift. Hand-edited for now.
 */

export interface UserResponse {
  id: number;
  username: string;
  role: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  user: UserResponse;
}

export type Confidence = "high" | "medium" | "low";

export interface SlotValueDto {
  slot_key: string;
  label: string;
  value: string | null;
  raw_value: number | null;
  unit: string | null;
  confidence: Confidence;
  source: string | null;
  source_url: string | null;
}

export interface GenerationStatusResponse {
  run_id: number;
  status: string;
  meeting_date: string; // ISO YYYY-MM-DD
  slots: SlotValueDto[];
  has_output: boolean;
  notes?: string | null;
}

export interface GenerationStartRequest {
  meeting_date: string;
  fengxing_open_date?: string;
}

export interface InternalDataRequest {
  data: Record<string, string>;
  meeting_time?: string;
}

// ──────── 中鋼盤價 admin ────────

export interface CscRow {
  slot_index: number;
  product_name: string;
  prev_price: number;
  change_amount: number;
  new_price: number;
}

export interface CscSnapshot {
  group: "monthly" | "quarterly";
  period_label: string;
  announce_date: string;
  rows: CscRow[];
}

export interface CscSaveRequest {
  period_label: string;
  announce_date: string;
  rows: { slot_index: number; prev_price: number; change_amount: number }[];
}

// ──────── User admin ────────

export interface AdminUser {
  id: number;
  username: string;
  role: "admin" | "user";
  is_active: boolean;
  created_at: string;   // ISO datetime
  last_login: string | null;
}

export interface CreateUserRequest {
  username: string;
  password: string;
  role: "admin" | "user";
}

export interface UpdateUserRequest {
  role?: "admin" | "user";
  is_active?: boolean;
}

export interface ResetPasswordRequest {
  password: string;
}

// ──────── Usage ────────

export interface UsageRow {
  username: string;
  runs_total: number;
  runs_success: number;
  runs_failed: number;
  last_run_at: string | null;
}
