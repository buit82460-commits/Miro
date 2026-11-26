"use client";
import { MiroShell } from "@/components/miro-shell";
import { BrowserPage } from "@/features/browser/BrowserPage";

export default function BrowserPageDetailRoute() {
  return (
    <MiroShell>
      <BrowserPage />
    </MiroShell>
  );
}
