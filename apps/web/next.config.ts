import type { NextConfig } from "next";

// Khi NEXT_PUBLIC_API_BASE trỏ sang BE thật, proxy /api/:path* sang BE
// (BE phục vụ /studio, /projects trực tiếp, không có prefix /api).
// Không có env → rewrites rỗng, giữ nguyên fixture nội bộ.
const apiBase = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    if (!apiBase) return [];
    // beforeFiles: uu tien hon route noi bo /api/* (fixture),
    // de trang live noi BE that qua cung prefix /api.
    return { beforeFiles: [{ source: "/api/:path*", destination: `${apiBase}/:path*` }] };
  },
};

export default nextConfig;
