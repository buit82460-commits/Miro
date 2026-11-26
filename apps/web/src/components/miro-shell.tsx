"use client";

import { Suspense } from "react";
import type { ReactNode } from "react";
import { AppShell } from "@/components/miro-layout/AppShell";

export function MiroShell({ children }: { children: ReactNode }) {
  return (
    <AppShell>
      <Suspense fallback={null}>{children}</Suspense>
    </AppShell>
  );
}
