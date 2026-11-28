import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  HealthService,
  RuntimeService,
  ScheduleService,
  type BeTaskSubmit,
  type RunMessageOut,
} from "@/lib/services/runtime.service";

export function useRuntimeStatus(pollMs = 2000) {
  return useQuery({
    queryKey: ["runtime", "status"],
    queryFn: () => RuntimeService.status(),
    refetchInterval: pollMs,
  });
}

export function useBeTasks(limit = 20, pollMs = 2000) {
  return useQuery({
    queryKey: ["runtime", "tasks", limit],
    queryFn: () => RuntimeService.recent(limit),
    refetchInterval: pollMs,
  });
}

export function useBeTask(id?: string, pollMs = 2000) {
  return useQuery({
    queryKey: ["runtime", "task", id],
    queryFn: () => RuntimeService.get(id!),
    enabled: !!id,
    refetchInterval: pollMs,
  });
}

export function useBeEvents(id?: string, pollMs = 1500) {
  return useQuery({
    queryKey: ["runtime", "events", id],
    queryFn: () => RuntimeService.events(id!),
    enabled: !!id,
    refetchInterval: pollMs,
  });
}

export function useRunMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { message: string; tabId: number; liveOrigin?: string; limit?: number }): Promise<RunMessageOut> =>
      RuntimeService.runMessage(args.message, args.tabId, args.liveOrigin ?? "", args.limit),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runtime", "tasks"] });
      qc.invalidateQueries({ queryKey: ["runtime", "status"] });
    },
  });
}

export function useCreateBeTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: BeTaskSubmit) => RuntimeService.create(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runtime", "tasks"] });
      qc.invalidateQueries({ queryKey: ["runtime", "status"] });
    },
  });
}

function invalidateTask(qc: ReturnType<typeof useQueryClient>, id: string) {
  qc.invalidateQueries({ queryKey: ["runtime", "task", id] });
  qc.invalidateQueries({ queryKey: ["runtime", "events", id] });
  qc.invalidateQueries({ queryKey: ["runtime", "tasks"] });
}

export function useBeStop() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => RuntimeService.stop(id),
    onSuccess: (_r, id) => invalidateTask(qc, id),
  });
}

export function useBeWaitStop() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, graceSeconds }: { id: string; graceSeconds?: number }) =>
      RuntimeService.waitStop(id, graceSeconds),
    onSuccess: (_r, v) => invalidateTask(qc, v.id),
  });
}

export function useBeRestart() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => RuntimeService.restart(id),
    onSuccess: (_r, id) => invalidateTask(qc, id),
  });
}

export function useBeResume() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => RuntimeService.resume(id),
    onSuccess: (_r, id) => invalidateTask(qc, id),
  });
}

export function useBeApprove() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: string; item?: number; scope?: string; revision?: number }) =>
      RuntimeService.approve(args.id, args.item ?? 0, args.scope ?? "edit", args.revision ?? 1),
    onSuccess: (_r, v) => invalidateTask(qc, v.id),
  });
}

export function useBeRevoke() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, item }: { id: string; item?: number }) => RuntimeService.revoke(id, item ?? 0),
    onSuccess: (_r, v) => invalidateTask(qc, v.id),
  });
}

// ---- Schedule (day-plan, SCH-01..03) ----
export function useDayPlan(pollMs = 5000) {
  return useQuery({
    queryKey: ["schedule", "day-plan"],
    queryFn: () => ScheduleService.dayPlan(),
    refetchInterval: pollMs,
    retry: false,
  });
}

export function useEnsureDayPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof ScheduleService.ensure>[0]) => ScheduleService.ensure(input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schedule", "day-plan"] });
    },
  });
}

export function useDayPlanStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (status: "active" | "paused") => ScheduleService.setStatus(status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["schedule", "day-plan"] });
    },
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => HealthService.check(),
    refetchInterval: 5000,
    retry: false,
  });
}
