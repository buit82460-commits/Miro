"use client";
import { MiroShell } from "@/components/miro-shell";
import { SettingsPage } from "@/features/settings/SettingsPage";

export default function SettingsPageRoute() {
  return (
    <MiroShell>
      <SettingsPage />
    </MiroShell>
  );
}
