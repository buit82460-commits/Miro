import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  RuntimeService,
  type RunMessageOut,
} from "@/lib/services/runtime.service";

export function useRuntimeStatus(pollMs = 5000) {
  return useQuery({
    queryKey: ["runtime", "status"],
    queryFn: () => RuntimeService.status(),
    refetchInterval: pollMs,
  });
}

export function useBeTasks(limit = 20, pollMs = 5000) {
  return useQuery({
    queryKey: ["runtime", "tasks", limit],
    queryFn: () => RuntimeService.recent(limit),
    refetchInterval: pollMs,
  });
}

export function useBeTask(id?: string, pollMs = 3000) {
  return useQuery({
    queryKey: ["runtime", "task", id],
    queryFn: () => RuntimeService.get(id!),
    enabled: !!id,
    refetchInterval: pollMs,
  });
}

export function useBeEvents(id?: string, pollMs = 3000) {
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
    mutationFn: (args: { message: string; tabId: number; liveOrigin?: string }): Promise<RunMessageOut> =>
      RuntimeService.runMessage(args.message, args.tabId, args.liveOrigin ?? ""),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runtime", "tasks"] });
      qc.invalidateQueries({ queryKey: ["runtime", "status"] });
    },
  });
}

export function useBeStop() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => RuntimeService.stop(id),
    onSuccess: (_r, id) => {
      qc.invalidateQueries({ queryKey: ["runtime", "task", id] });
      qc.invalidateQueries({ queryKey: ["runtime", "tasks"] });
    },
  });
}
