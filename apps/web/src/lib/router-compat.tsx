"use client";

import Link from "next/link";
import {
  useParams as useNextParams,
  usePathname,
  useRouter,
  useSearchParams as useNextSearchParams,
} from "next/navigation";
import { useEffect } from "react";
import type { ReactNode, MouseEvent } from "react";
import { cn } from "@/lib/utils";

export function useNavigate() {
  const router = useRouter();
  return (to: string) => router.push(to);
}

export function useLocation() {
  const pathname = usePathname();
  return { pathname };
}

export function useParams<T extends Record<string, string> = Record<string, string>>() {
  const p = useNextParams();
  return (p ?? {}) as T;
}

export function useSearchParams() {
  const sp = useNextSearchParams();
  const get = (k: string) => sp?.get(k) ?? null;
  return [ { get } ] as const;
}

export function Navigate({ to }: { to: string }) {
  const router = useRouter();
  useEffect(() => {
    router.replace(to);
  }, [router, to]);
  return null;
}

type NavLinkProps = {
  to: string;
  children: ReactNode;
  className?: string | ((props: { isActive: boolean }) => string);
  title?: string;
  onClick?: (e: MouseEvent) => void;
  end?: boolean;
};

export function NavLink({ to, children, className, title, onClick, end }: NavLinkProps) {
  const pathname = usePathname();
  const isActive = end ? pathname === to : pathname === to || pathname.startsWith(`${to}/`);
  const resolved = typeof className === "function" ? className({ isActive }) : className;
  return (
    <Link
      href={to}
      title={title}
      onClick={onClick}
      className={cn(resolved)}
      aria-current={isActive ? "page" : undefined}
    >
      {children}
    </Link>
  );
}

export { Link };
export function Outlet() {
  return null;
}
export function BrowserRouter({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
export function Routes({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
export function Route() {
  return null;
}
