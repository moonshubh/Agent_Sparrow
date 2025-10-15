import { NextRequest } from "next/server";
import { verifyZendeskAdminAccess } from "@/services/security/zendesk-admin-auth";

const jsonHeaders = { "Content-Type": "application/json" };

function buildAuthError(reason: "not_authenticated" | "forbidden" | "unsupported") {
  const status = reason === "forbidden" ? 403 : reason === "unsupported" ? 500 : 401;
  return new Response(JSON.stringify({ error: reason }), { status, headers: jsonHeaders });
}

export async function POST(_req: NextRequest, ctx: { params: { id: string } }) {
  const auth = await verifyZendeskAdminAccess();
  if (!auth.ok) {
    return buildAuthError(auth.reason ?? "not_authenticated");
  }

  const apiBase = process.env.API_BASE;
  const token = process.env.INTERNAL_API_TOKEN;
  if (!apiBase || !token) {
    return new Response(JSON.stringify({ error: "server_config_missing" }), { status: 500, headers: jsonHeaders });
  }
  const id = ctx.params.id;
  const url = `${apiBase}/api/v1/integrations/zendesk/admin/queue/${encodeURIComponent(id)}/retry`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "X-Internal-Token": token },
    cache: "no-store",
  });
  const text = await res.text();
  return new Response(text, { status: res.status, headers: { "Content-Type": res.headers.get("content-type") || "application/json" } });
}
