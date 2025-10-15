"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { requireAdminApiConfig } from "../../api/admin/zendesk/_shared/admin-api-config";
import { verifyZendeskAdminAccess } from "@/services/security/zendesk-admin-auth";

export async function retryTicketAction(formData: FormData) {
  const auth = await verifyZendeskAdminAccess();
  if (!auth.ok) {
    if (auth.reason === "not_authenticated") {
      redirect("/login?returnUrl=/settings/zendesk");
    }
    throw new Error(auth.reason || "forbidden");
  }

  const ticketId = formData.get("id");
  if (!ticketId) {
    throw new Error("missing ticket id");
  }

  const { apiBase, token } = requireAdminApiConfig();
  let response: Response;
  try {
    response = await fetch(
      `${apiBase}/api/v1/integrations/zendesk/admin/queue/${encodeURIComponent(String(ticketId))}/retry`,
      {
        method: "POST",
        headers: { "X-Internal-Token": token },
        cache: "no-store",
      },
    );
  } catch (error) {
    throw new Error("retry_network_error");
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `retry_failed_${response.status}`);
  }

  revalidatePath("/settings/zendesk");
}
