import { NextRequest } from "next/server";
import {
  validateAdminAccess,
  getAdminConfig,
  callUpstream,
} from "../_shared/route-helpers";

export async function GET(req: NextRequest) {
  const authError = await validateAdminAccess();
  if (authError) {
    return authError;
  }

  const configResult = getAdminConfig();
  if (configResult instanceof Response) {
    return configResult;
  }

  const { searchParams } = new URL(req.url);
  const status = searchParams.get("status") || "";
  const limit = searchParams.get("limit") || "50";
  const offset = searchParams.get("offset") || "0";

  return callUpstream(
    "/api/v1/integrations/zendesk/admin/queue",
    configResult,
    {
      searchParams: { status, limit, offset },
    },
  );
}

export async function POST(req: NextRequest) {
  const authError = await validateAdminAccess();
  if (authError) {
    return authError;
  }

  const configResult = getAdminConfig();
  if (configResult instanceof Response) {
    return configResult;
  }

  const body = await req.text();
  return callUpstream(
    "/api/v1/integrations/zendesk/admin/queue/retry-batch",
    configResult,
    {
      method: "POST",
      body,
      headers: { "Content-Type": "application/json" },
    },
  );
}
