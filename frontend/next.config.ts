import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow LAN / Tailscale clients to load HMR + RSC payload assets in dev.
  // Next.js 16 blocks cross-origin dev requests by default for safety.
  // Add any IP / hostname your colleagues use to reach this machine.
  // Wildcards (e.g. "*.tail-something.ts.net") are supported.
  allowedDevOrigins: [
    "100.85.183.15",      // 使用者 Tailscale / LAN IP
    "192.168.*",          // 一般家用/辦公室內網
    "10.*",               // 私有網段 10.x
    "172.16.*",           // Docker default
    "*.ts.net",           // Tailscale magicdns
  ],

  // When API_PROXY_TARGET is set (production deploy), the frontend's Node
  // server proxies /api/* to the FastAPI backend. This keeps every request
  // same-origin from the browser's perspective — no CORS, no cross-site
  // cookies, no SameSite=None third-party blocking. Browsers store the
  // backend's Set-Cookie under the frontend domain and re-send it on every
  // subsequent /api/* call. Local dev leaves API_PROXY_TARGET unset and the
  // existing NEXT_PUBLIC_API_BASE fallback in lib/api.ts handles direct
  // calls to http://localhost:8001.
  async rewrites() {
    const target = process.env.API_PROXY_TARGET;
    if (!target) return [];
    return [
      { source: "/api/:path*", destination: `${target}/api/:path*` },
    ];
  },
};

export default nextConfig;
