import { useQuery } from "@tanstack/react-query";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const res = await fetch("/api/health");
      if (!res.ok) throw new Error("health check failed");
      return (await res.json()) as { status: string };
    },
  });
}
