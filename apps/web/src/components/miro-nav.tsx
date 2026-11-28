"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const LINKS = [
  { href: "/", label: "Công việc" },
  { href: "/tasks-live", label: "Giao việc (live)" },
  { href: "/runtime", label: "Runtime" },
  { href: "/library", label: "Thư viện" },
  { href: "/publish", label: "Xuất bản" },
  { href: "/editor", label: "Editor" },
  { href: "/settings", label: "Cài đặt & kết nối" },
  { href: "/settings/connections", label: "Kết nối" },
  { href: "/settings/platforms", label: "Nền tảng" },
  // BUG-03: link chéo sang shell mới (AppShell) — 2 nav không còn cô lập.
  { href: "/workspace", label: "AI Workspace (mới)" },
  { href: "/tasks", label: "Tác vụ (mới)" },
  { href: "/overview", label: "Tổng quan (mới)" },
];

export default function MiroNav({ children }: { children: ReactNode }) {
  const path = usePathname();
  return (
    <div style={{ display: "flex", minHeight: "100vh" }} suppressHydrationWarning>
      <aside
        data-testid="miro-sidebar"
        style={{ width: 220, borderRight: "1px solid #ddd", padding: 16, background: "#fff" }}
        suppressHydrationWarning
      >
        <div style={{ fontWeight: 800, fontSize: 20, marginBottom: 16 }} suppressHydrationWarning>Miro</div>
        <nav style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              data-testid={`nav-${l.href === "/" ? "tasks" : l.href.slice(1)}`}
              style={{
                padding: "8px 12px",
                borderRadius: 8,
                textDecoration: "none",
                background: path === l.href ? "#16161a" : "transparent",
                color: path === l.href ? "#fff" : "#16161a",
                fontWeight: 600,
              }}
            >
              {l.label}
            </Link>
          ))}
        </nav>
      </aside>
      <main style={{ flex: 1, padding: 24, maxWidth: 1200 }} suppressHydrationWarning>{children}</main>
    </div>
  );
}
