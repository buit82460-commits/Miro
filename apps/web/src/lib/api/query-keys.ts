// BE sở hữu state — mọi cache FE đều đi qua các key này.
export const QUERY_KEYS = {
  tasks: ["tasks"] as const,
  taskList: (params?: Record<string, string>) => [...QUERY_KEYS.tasks, "list", params ?? {}] as const,
  taskDetail: (id: string) => [...QUERY_KEYS.tasks, "detail", id] as const,
  library: ["library"] as const,
  libraryList: () => [...QUERY_KEYS.library, "list"] as const,
  publish: ["publish"] as const,
  receipts: () => [...QUERY_KEYS.publish, "receipts"] as const,
  publishBatches: () => [...QUERY_KEYS.publish, "batches"] as const,
  projects: ["projects"] as const,
  projectDetail: (id: string) => [...QUERY_KEYS.projects, "detail", id] as const,
  connections: ["settings", "connections"] as const,
  connectionDetail: (id: string) => [...QUERY_KEYS.connections, "detail", id] as const,
  connectionDefault: (platform: string) => [...QUERY_KEYS.connections, "default", platform] as const,
  platforms: ["settings", "platforms"] as const,
  platformsHistory: () => [...QUERY_KEYS.platforms, "history"] as const,
} as const;
