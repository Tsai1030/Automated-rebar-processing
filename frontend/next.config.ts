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
};

export default nextConfig;
