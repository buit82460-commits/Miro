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
