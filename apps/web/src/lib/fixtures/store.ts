// Fixture/mock nội bộ theo contract BE. Chạy dev + E2E không cần runtime thật.
// Khi nối runtime thật: trỏ NEXT_PUBLIC_API_BASE sang BE, các route này không dùng nữa.

export type FixtureTask = {
  id: string;
  title: string;
  status: "queued" | "running" | "awaiting_review" | "approved" | "stopped" | "done";
  revision: number;
  updated_at: string;
};

export type FixtureClip = {
  id: string;
  kind: "video" | "audio" | "text";
  start: number;
  duration: number;
  text?: string;
};

export type FixtureProject = {
  id: string;
  title: string;
  revision: number;
  duration: number;
  canvas: { width: number; height: number };
  tracks: { id: string; kind: string; clips: FixtureClip[] }[];
  render?: { job_id: string; status: string; preview: boolean };
  approved?: boolean;
};

export type FixtureBatch = {
  id: string;
  video_id: string;
  platform: string;
  account: string;
  scheduled_at?: string;
  status: string;
};

export type FixtureReceipt = {
  id: string;
  post_id?: string;
  post_url?: string;
  platform: string;
  account: string;
  status: "posted" | "scheduled" | "failed" | "unknown";
  posted_at?: string;
};

const now = () => new Date().toISOString();

function seedProject(id: string, title: string): FixtureProject {
  return {
    id,
    title,
    revision: 3,
    duration: 20,
    canvas: { width: 1080, height: 1920 },
    tracks: [
      {
        id: "t-video",
        kind: "video",
        clips: [{ id: "c1", kind: "video", start: 0, duration: 20 }],
      },
      {
        id: "t-text",
        kind: "text",
        clips: [
          { id: "sub1", kind: "text", start: 0, duration: 2, text: "Xin chào Threads" },
          { id: "sub2", kind: "text", start: 2, duration: 2, text: "Video thử nghiệm" },
        ],
      },
    ],
  };
}

// Module-level store: tồn tại suốt dev-server / E2E webServer.
const store: {
  tasks: FixtureTask[];
  projects: FixtureProject[];
  batches: FixtureBatch[];
  receipts: FixtureReceipt[];
  history: { at: string; event: string; detail: string }[];
  seq: number;
} = {
  tasks: [
    { id: "task-1", title: "Dựng video Threads mở đầu", status: "awaiting_review", revision: 2, updated_at: now() },
  ],
  projects: [seedProject("p1", "Video Threads mở đầu"), seedProject("p2", "Video kho thứ hai")],
  batches: [],
  receipts: [],
  history: [{ at: now(), event: "seed", detail: "fixture khởi tạo" }],
  seq: 100,
};

export function getStore() {
  return store;
}

export function nextId(prefix: string) {
  store.seq += 1;
  return `${prefix}-${store.seq}`;
}

export function pushHistory(event: string, detail: string) {
  store.history.unshift({ at: now(), event, detail });
}

export function resetFixture() {
  store.tasks = [
    { id: "task-1", title: "Dựng video Threads mở đầu", status: "awaiting_review", revision: 2, updated_at: now() },
  ];
  store.projects = [seedProject("p1", "Video Threads mở đầu"), seedProject("p2", "Video kho thứ hai")];
  store.batches = [];
  store.receipts = [];
  store.history = [{ at: now(), event: "seed", detail: "fixture khởi tạo" }];
  store.seq = 100;
}

export function ok<T>(result: T, status = 200) {
  return Response.json({ success: true, result }, { status });
}

export function fail(message: string, status = 400) {
  return Response.json({ success: false, error: message }, { status });
}
