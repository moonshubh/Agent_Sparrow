import { requireAdminApiConfig } from "../_shared/admin-api-config";
import { verifyZendeskAdminAccess } from "@/services/security/zendesk-admin-auth";

const jsonHeaders = { "Content-Type": "application/json" };

function buildAuthError(reason: "not_authenticated" | "forbidden" | "unsupported") {
  const status = reason === "forbidden" ? 403 : reason === "unsupported" ? 500 : 401;
  return new Response(JSON.stringify({ error: reason }), { status, headers: jsonHeaders });
}

export async function GET() {
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

  const url = `${config.apiBase}/api/v1/integrations/zendesk/models`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: "GET",
      headers: { "X-Internal-Token": config.token },
      cache: "no-store",
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: "upstream_unreachable" }), { status: 502, headers: jsonHeaders });
  }
  const text = await res.text();
  return new Response(text, { status: res.status, headers: { "Content-Type": res.headers.get("content-type") || "application/json" } });
}
