import { NextRequest } from "next/server";
import {
  validateAdminAccess,
  getAdminConfig,
  callUpstream,
} from "../../../_shared/route-helpers";

export async function POST(
  _req: NextRequest,
  ctx: { params: Promise<{ id: string }> },
) {
  const authError = await validateAdminAccess();
  if (authError) {
    return authError;
  }

  const configResult = getAdminConfig();
  if (configResult instanceof Response) {
    return configResult;
  }

  const { id } = await ctx.params;
  return callUpstream(
    `/api/v1/integrations/zendesk/admin/queue/${encodeURIComponent(id)}/retry`,
    configResult,
    {
      method: "POST",
    },
  );
}
