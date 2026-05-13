/**
 * Single fetch wrapper for talking to the FastAPI backend.
 *
 * Why credentials: "include" matters:
 *   The backend sets HttpOnly cookies for JWT. Browsers only send those
 *   cookies cross-origin when fetch is called with credentials: "include"
 *   AND the backend responds with Access-Control-Allow-Credentials: true.
 *   Both halves are required — missing either silently fails.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8001";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });

  if (!res.ok) {
    // Read the body exactly once — Response.body is a one-shot stream, so
    // calling .json() and then falling back to .text() on the same Response
    // throws "body stream already read". Take the raw text first, then
    // attempt to parse it as JSON.
    const raw = await res.text();
    let body: unknown = raw;
    try {
      body = JSON.parse(raw);
    } catch {
      /* leave as raw text */
    }
    if (res.status === 401 && typeof window !== "undefined") {
      // Hard redirect — let the proxy/route guard re-evaluate auth state.
      window.location.href = "/login";
    }
    // Surface the backend's `detail` field (FastAPI's default error shape)
    // in the message so generate-view's plain `error.message` toast is
    // informative without each caller having to dig into `error.body`.
    const detail =
      body && typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : typeof body === "string" && body.length > 0 && body.length < 500
          ? body
          : null;
    const message = detail
      ? `API ${res.status}: ${detail}`
      : `API ${res.status}: ${path}`;
    throw new ApiError(res.status, body, message);
  }

  // Some endpoints (logout) return JSON; binary downloads (Word) caller
  // should bypass this helper and use fetch directly.
  return res.json() as Promise<T>;
}

export const apiBase = API_BASE;
