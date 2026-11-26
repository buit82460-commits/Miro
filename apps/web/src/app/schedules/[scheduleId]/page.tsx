"use client";
import { MiroShell } from "@/components/miro-shell";
import { SchedulesPage } from "@/features/schedules/SchedulesPage";

export default function SchedulesPageDetailRoute() {
  return (
    <MiroShell>
      <SchedulesPage />
    </MiroShell>
  );
}
