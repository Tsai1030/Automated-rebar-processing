/**
 * Next.js 16 Proxy (formerly "middleware") — protects routes by checking
 * the presence of the access_token cookie set by the FastAPI backend.
 *
 * IMPORTANT — this is an OPTIMISTIC check only.
 * The cookie is HttpOnly so we can't read or verify the JWT here. We only
 * check that the cookie exists. Actual JWT verification happens on the
 * backend on every API call. Per Next.js 16 docs:
 *   "Proxy is not intended for slow data fetching ... it should not be
 *    used as a full session management or authorization solution."
 */
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login"];

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
  const hasToken = request.cookies.has("access_token");

  if (!hasToken && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("redirect", pathname);
    return NextResponse.redirect(url);
  }

  if (hasToken && isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/generate";
    url.searchParams.delete("redirect");
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // Run on everything except Next internals, static assets, and the /api
  // proxy. /api/* must skip this proxy entirely — those requests are
  // forwarded to the FastAPI backend via next.config.ts rewrites, and the
  // backend does its own JWT verification. If we ran this proxy on /api/*
  // unauthenticated calls to /api/auth/login would 307→/login→405 (POST
  // can't reach a page route).
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
