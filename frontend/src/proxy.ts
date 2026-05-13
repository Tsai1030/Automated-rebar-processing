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
  // Run on everything except Next internals and static assets.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"],
};
