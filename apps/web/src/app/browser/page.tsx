"use client";
import { MiroShell } from "@/components/miro-shell";
import { BrowserPage } from "@/features/browser/BrowserPage";

export default function BrowserPageRoute() {
  return (
    <MiroShell>
      <BrowserPage />
    </MiroShell>
  );
}
