"use client";
import type { ReactNode } from "react";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import "./youcare.css";

const MAIN_TABS = [
  { href: "/overview", label: "Tổng quan" },
  { href: "/tasks", label: "Tác vụ" },
  { href: "/publishing", label: "Xuất bản" },
  { href: "/schedules", label: "Lịch hẹn" },
  { href: "/browser", label: "Trình duyệt" },
];

const EXTRA_LINKS = [
  { href: "/tasks-live", label: "Giám sát live" },
  { href: "/runtime", label: "Runtime" },
  { href: "/projects", label: "Dự án" },
  { href: "/media", label: "Media" },
  { href: "/research", label: "Nghiên cứu" },
  { href: "/workflows", label: "Quy trình" },
  { href: "/knowledge", label: "Tri thức" },
  { href: "/activity", label: "Hoạt động" },
  { href: "/integrations", label: "Tích hợp" },
  { href: "/settings", label: "Cài đặt" },
];

export function YoucareShell({ children, title, subtitle, actions, crumb }: { children: ReactNode; title?: string; subtitle?: string; actions?: ReactNode; crumb?: string }) {
  const path = usePathname() ?? "";
  const [menuOpen, setMenuOpen] = useState(false);
  const activeExtra = EXTRA_LINKS.find((t) => path === t.href || (t.href !== "/overview" && path.startsWith(t.href + "/")));
  return (
    <div className="yc-page">
    <div className="yc-shell">
      <div className="yc-top">
        <Link href="/overview" style={{ textDecoration: "none" }}><div className="yc-logo"><span className="yc-mk">M</span><span><b>Miro</b><small>Không gian vận hành AI</small></span></div></Link>
        <nav className="yc-tabs">
          {MAIN_TABS.map((t) => (
            <Link key={t.href} href={t.href} className={path === t.href || path.startsWith(t.href + "/") ? "on" : ""}>{t.label}</Link>
          ))}
        </nav>
        <div className="yc-hicons">
          <span className="yc-hic" title="Tìm kiếm">⌕</span>
          <span className="yc-hic" title="Thông báo">🔔</span>
          <Link className="yc-hic" style={{ textDecoration: "none" }} title="Cài đặt" href="/settings">⚙</Link>
          <span className="yc-hic" title="Trang khác" onClick={() => setMenuOpen((v) => !v)} style={{ cursor: "pointer" }}>⋯</span>
        </div>
      </div>
      {menuOpen ? (
        <div className="yc-menu">
          {EXTRA_LINKS.map((t) => (
            <Link key={t.href} href={t.href} className={path.startsWith(t.href) ? "on" : ""} onClick={() => setMenuOpen(false)}>{t.label}</Link>
          ))}
        </div>
      ) : null}
      {title ? (
        <div className="yc-hello">
          <div><h1>{title}</h1>{subtitle ? <p>{subtitle}</p> : null}</div>
          <div className="yc-hr">{actions}</div>
        </div>
      ) : null}
      <div className="yc-crumb">Miro / <b>{crumb ?? activeExtra?.label ?? MAIN_TABS.find((t) => path.startsWith(t.href))?.label ?? "Tổng quan"}</b></div>
      <div className="yc-body">{children}</div>
    </div>
    </div>
  );
}

export function StatCard({ label, value, sub, tone }: { label: string; value: string; sub?: ReactNode; tone?: "blue" }) {
  return (
    <div className="yc-card">
      <h4>{label}</h4>
      <div className="yc-bign" style={tone === "blue" ? { color: "#3b32f0" } : undefined}>{value}</div>
      {sub ? <div className="yc-sub">{sub}</div> : null}
    </div>
  );
}

export function EmptyState({ text }: { text: string }) {
  return <div className="yc-empty">{text}</div>;
}
