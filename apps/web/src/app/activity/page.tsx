"use client";
import { MiroShell } from "@/components/miro-shell";
import { ActivityPage } from "@/features/activity/ActivityPage";

export default function ActivityPageRoute() {
  return (
    <MiroShell>
      <ActivityPage />
    </MiroShell>
  );
}
