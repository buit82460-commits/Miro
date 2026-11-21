import { NextResponse } from "next/server";

const BACKEND = process.env.MIRO_API_BASE ?? "http://localhost:8000";

async function passthrough(path: string, init?: RequestInit) {
  const res = await fetch(`${BACKEND}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}

export async function GET() {
  return passthrough("/platforms");
}

export async function POST(req: Request) {
  return passthrough("/platforms", { method: "POST", body: await req.text() });
}
