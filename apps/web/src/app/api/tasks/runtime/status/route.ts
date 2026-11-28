import { beFetch, beForward, beUnavailable } from "@/lib/be-proxy";

// GET /api/tasks/runtime/status — runtime + bridge wiring (redacted, không key).
export async function GET() {
  const be = await beFetch("/tasks/runtime/status");
  if (be.ok) return beForward(be.status, be.body);
  return beUnavailable();
}
