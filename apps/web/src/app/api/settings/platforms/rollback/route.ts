import { NextResponse } from "next/server";

const BACKEND = process.env.MIRO_API_BASE ?? "http://localhost:8000";

export async function POST(req: Request) {
  const body = await req.text();
  const res = await fetch(`${BACKEND}/platforms/rollback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  return NextResponse.json(await res.json().catch(() => ({})), { status: res.status });
}
