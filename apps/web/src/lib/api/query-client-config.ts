import type { QueryClientConfig } from "@tanstack/react-query";

// BE sở hữu state qua Query key; Editor local chỉ giữ playhead/kéo-thả.
const queryClientConfig: QueryClientConfig = {
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5,
      gcTime: 1000 * 60 * 4,
      retry: 1,
      refetchOnWindowFocus: true,
      refetchOnMount: true,
      refetchInterval: false,
      refetchOnReconnect: false,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 60 * 1000),
    },
    mutations: {
      retry: 0,
      onError: (error) => {
        console.log("Mutation Error:", error);
      },
    },
  },
};

export default queryClientConfig;
