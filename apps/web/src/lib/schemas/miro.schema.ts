import { z } from "zod";

// Contract FE<->BE (dùng cho cả fixture/mock lẫn runtime thật).

export const taskSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: z.enum(["queued", "running", "awaiting_review", "approved", "stopped", "done"]),
  revision: z.number(),
  updated_at: z.string().optional(),
});
export type TaskItem = z.infer<typeof taskSchema>;

export const chatSendSchema = z.object({
  message: z.string().min(1, "Nhập nội dung chat").max(4000),
  task_id: z.string().optional(),
});
export type ChatSendInput = z.infer<typeof chatSendSchema>;

export const reviewSchema = z.object({
  decision: z.enum(["approve", "reject", "stop"]),
  note: z.string().max(2000).default(""),
});
export type ReviewInput = z.infer<typeof reviewSchema>;

export const subtitleSchema = z.object({
  start: z.coerce.number().min(0),
  end: z.coerce.number().min(0),
  text: z.string().min(1, "Nhập nội dung phụ đề").max(500),
});
export type SubtitleInput = z.infer<typeof subtitleSchema>;

export const publishBatchSchema = z.object({
  video_id: z.string().min(1, "Chọn video"),
  platform: z.enum(["threads", "facebook", "tiktok", "youtube", "instagram"]),
  account: z.string().min(1, "Chọn tài khoản"),
  scheduled_at: z.string().optional(),
});
export type PublishBatchInput = z.infer<typeof publishBatchSchema>;

export const receiptSchema = z.object({
  id: z.string(),
  post_id: z.string().optional(),
  post_url: z.string().optional(),
  platform: z.string(),
  account: z.string(),
  status: z.enum(["posted", "scheduled", "failed", "unknown"]),
  posted_at: z.string().optional(),
});
export type Receipt = z.infer<typeof receiptSchema>;

const capabilitySchema = z.object({
  status: z.string(),
  runtime: z.string(),
  input: z.string(),
  output: z.string(),
  evidence: z.string(),
});

export const platformSchema = z.object({
  id: z.string(),
  name: z.string(),
  version: z.number(),
  runtime: z.string(),
  accounts: z.array(z.string()),
  entry_urls: z.record(z.string(), z.string()),
  capabilities: z.record(z.string(), capabilitySchema),
  tracks: z.object({ read: z.string(), publish: z.string() }),
});
export type PlatformItem = z.infer<typeof platformSchema>;

export const registrySchema = z.object({
  version: z.number(),
  platforms: z.array(platformSchema),
});
export type Registry = z.infer<typeof registrySchema>;

export const platformUpsertSchema = z.object({
  id: z
    .string()
    .min(1, "Nhập id platform")
    .max(40)
    .regex(/^[a-z0-9-]+$/, "id chỉ gồm chữ thường, số và gạch ngang"),
  name: z.string().min(1, "Nhập tên hiển thị").max(80),
  runtime: z.string().min(1, "Nhập runtime/adapter").max(200),
  accounts: z
    .array(z.string().min(1).max(120))
    .max(20, "Tối đa 20 tài khoản")
    .default([]),
  track_read: z.enum(["READY", "DEGRADED", "UNKNOWN"]).default("UNKNOWN"),
  track_publish: z.enum(["READY", "DEGRADED", "BLOCKED", "UNKNOWN"]).default("UNKNOWN"),
  capabilities: z
    .array(
      z.object({
        key: z.enum(["list", "download", "draft", "publish", "reconcile", "watch"]),
        status: z.enum(["SUPPORTED", "PARTIAL", "BLOCKED", "UNKNOWN"]),
        runtime: z.string().max(200).default("fixture"),
        input: z.string().max(120).default(""),
        output: z.string().max(120).default(""),
        evidence: z.string().max(500).default(""),
      }),
    )
    .max(6)
    .default([]),
});
export type PlatformUpsertInput = z.infer<typeof platformUpsertSchema>;

export const platformCloneSchema = z.object({
  new_id: z
    .string()
    .max(40)
    .regex(/^[a-z0-9-]*$/, "new_id chỉ gồm chữ thường, số và gạch ngang")
    .default(""),
});
export type PlatformCloneInput = z.infer<typeof platformCloneSchema>;

export const rollbackSchema = z.object({
  version: z.coerce.number().int().min(1, "Nhập version cần rollback về"),
});
export type RollbackInput = z.infer<typeof rollbackSchema>;
