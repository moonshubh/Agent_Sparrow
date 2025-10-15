import { NextRequest } from "next/server";
import { requireAdminApiConfig } from "../_shared/admin-api-config";
import { verifyZendeskAdminAccess } from "@/services/security/zendesk-admin-auth";

const jsonHeaders = { "Content-Type": "application/json" };

function buildAuthError(reason: "not_authenticated" | "forbidden" | "unsupported") {
  const status = reason === "forbidden" ? 403 : reason === "unsupported" ? 500 : 401;
  return new Response(JSON.stringify({ error: reason }), { status, headers: jsonHeaders });
}

export async function GET(req: NextRequest) {
  const auth = await verifyZendeskAdminAccess();
  if (!auth.ok) {
    return buildAuthError(auth.reason ?? "not_authenticated");
  }

  let config;
  try {
    config = requireAdminApiConfig();
  } catch (error) {
    return new Response(JSON.stringify({ error: "server_config_missing" }), { status: 500, headers: jsonHeaders });
  }
  const { searchParams } = new URL(req.url);
  const status = searchParams.get("status") || "";
  const limit = searchParams.get("limit") || "50";
  const offset = searchParams.get("offset") || "0";
  const url = `${config.apiBase}/api/v1/integrations/zendesk/admin/queue?status=${encodeURIComponent(status)}&limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`;
  let res: Response;
  try {
    res = await fetch(url, {
      headers: { "X-Internal-Token": config.token },
      cache: "no-store",
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: "upstream_unreachable" }), { status: 502, headers: jsonHeaders });
  }
  const text = await res.text();
  const headers = new Headers({ "Content-Type": res.headers.get("content-type") || "application/json" });
  const total = res.headers.get("X-Total-Count");
  if (total) headers.set("X-Total-Count", total);
  return new Response(text, { status: res.status, headers });
}

export async function POST(req: NextRequest) {
  const auth = await verifyZendeskAdminAccess();
  if (!auth.ok) {
    return buildAuthError(auth.reason ?? "not_authenticated");
  }

  // Retry batch
  let config;
  try {
    config = requireAdminApiConfig();
  } catch (error) {
    return new Response(JSON.stringify({ error: "server_config_missing" }), { status: 500, headers: jsonHeaders });
  }
  const url = `${config.apiBase}/api/v1/integrations/zendesk/admin/queue/retry-batch`;
  const body = await req.text();
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "X-Internal-Token": config.token, "Content-Type": "application/json" },
      body,
      cache: "no-store",
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: "upstream_unreachable" }), { status: 502, headers: jsonHeaders });
  }
  const text = await res.text();
  return new Response(text, { status: res.status, headers: { "Content-Type": res.headers.get("content-type") || "application/json" } });
}
