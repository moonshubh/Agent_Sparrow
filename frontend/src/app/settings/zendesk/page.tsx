import { redirect } from "next/navigation";
import { buildAuthCookieHeader, verifyZendeskAdminAccess } from "@/services/security/zendesk-admin-auth";
import { retryTicketAction } from "./actions";
import { ZendeskStats } from "@/features/zendesk/components/ZendeskStats";
import { FeatureToggles } from "./FeatureToggles";

export const dynamic = "force-dynamic";

type QueueItem = {
  id: number;
  ticket_id: number;
  status: string;
  retry_count: number;
  created_at: string;
  last_attempt_at?: string | null;
  last_error?: string | null;
};

async function fetchJSON<T>(url: string): Promise<T> {
  const cookieHeader = buildAuthCookieHeader();
  const res = await fetch(url, {
    cache: "no-store",
    headers: cookieHeader ? { Cookie: cookieHeader } : undefined,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export default async function ZendeskSettingsPage() {
  const auth = await verifyZendeskAdminAccess();
  if (!auth.ok) {
    if (auth.reason === "not_authenticated") {
      redirect("/login?returnUrl=/settings/zendesk");
    }
    return (
      <div className="p-6">
        <h1 className="text-xl font-semibold">Zendesk Integration</h1>
        <p className="mt-2 text-sm text-red-500">Access denied. Please contact an administrator.</p>
      </div>
    );
  }

  let health: any = null;
  let queue: { items: QueueItem[]; total: number } = { items: [], total: 0 };
  let queueError: string | null = null;

  try {
    health = await fetchJSON("/api/admin/zendesk/health");
  } catch (err) {
    health = null;
  }

  try {
    queue = await fetchJSON("/api/admin/zendesk/queue?status=pending&limit=25&offset=0");
  } catch (err) {
    queueError = err instanceof Error ? err.message : "Failed to load queue";
  }

  return (
    <div className="p-6 space-y-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Zendesk Integration (Admin)</h1>
        <span className="text-xs text-muted-foreground">Logged in as {auth.user?.email ?? "admin"}</span>
      </header>

      {/* Stats summary */}
      <ZendeskStats
        health={{
          enabled: Boolean(health?.enabled),
          dry_run: Boolean(health?.dry_run),
          usage: health?.usage ?? null,
          daily: health?.daily ?? null,
          queue: health?.queue ?? null,
        }}
      />

      {/* Feature toggles */}
      {health && (
        <FeatureToggles
          initialEnabled={Boolean(health?.enabled)}
          initialDryRun={Boolean(health?.dry_run)}
        />
      )}

      <section className="rounded-md border p-4">
        <h2 className="font-medium">Status</h2>
        {health ? (
          <dl className="mt-3 grid gap-2 text-sm md:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Enabled</dt>
              <dd className="font-medium">{String(health.enabled)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Dry run</dt>
              <dd className="font-medium">{String(health.dry_run)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Last run</dt>
              <dd className="font-medium">{health?.scheduler?.last_run_at || "-"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Last success</dt>
              <dd className="font-medium">{health?.scheduler?.last_success_at || "-"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Last error</dt>
              <dd className="font-medium text-red-500">{health?.scheduler?.last_error || "-"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Queue counts</dt>
              <dd className="font-medium">
                pending={health?.queue?.pending ?? "-"}, retry={health?.queue?.retry ?? "-"}, processing={health?.queue?.processing ?? "-"}, failed={health?.queue?.failed ?? "-"}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Daily usage</dt>
              <dd className="font-medium">{health?.daily?.gemini_calls_used ?? "-"} / {health?.daily?.gemini_daily_limit ?? "-"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Monthly usage</dt>
              <dd className="font-medium">{health?.usage?.calls_used ?? "-"} / {health?.usage?.budget ?? "-"}</dd>
            </div>
          </dl>
        ) : (
          <p className="mt-2 text-sm text-red-500">Failed to load health metrics.</p>
        )}
      </section>

      <section className="rounded-md border p-4">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Pending Queue</h2>
          <span className="text-xs text-muted-foreground">Total: {queue.total}</span>
        </div>
        {queueError ? (
          <p className="mt-2 text-sm text-red-500">{queueError}</p>
        ) : queue.items.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">No pending tickets.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="bg-muted/40 text-left">
                  <th className="p-2">ID</th>
                  <th className="p-2">Ticket</th>
                  <th className="p-2">Status</th>
                  <th className="p-2">Retries</th>
                  <th className="p-2">Created</th>
                  <th className="p-2">Last Attempt</th>
                  <th className="p-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {queue.items.map((it) => (
                  <tr key={it.id} className="border-b">
                    <td className="p-2">{it.id}</td>
                    <td className="p-2">{it.ticket_id}</td>
                    <td className="p-2">{it.status}</td>
                    <td className="p-2">{it.retry_count}</td>
                    <td className="p-2">{new Date(it.created_at).toLocaleString()}</td>
                    <td className="p-2">{it.last_attempt_at ? new Date(it.last_attempt_at).toLocaleString() : "-"}</td>
                    <td className="p-2">
                      <form action={retryTicketAction} className="inline-flex gap-2">
                        <input type="hidden" name="id" value={it.id} />
                        <button className="rounded border px-2 py-1 text-xs hover:bg-muted" type="submit">
                          Retry
                        </button>
                      </form>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
