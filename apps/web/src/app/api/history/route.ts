import { getStore, ok } from "@/lib/fixtures/store";

export async function GET() {
  return ok(getStore().history);
}
