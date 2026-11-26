"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { AppShell } from "@/components/miro-layout/AppShell";

export function MiroShell({ children }: { children: ReactNode }) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  if (!mounted) return null;
  return (
    <AppShell>
      {children}
    </AppShell>
  );
}
