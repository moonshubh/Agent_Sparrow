import { useState } from "react";
import { LogAnalysisRequestBody, LogAnalysisResponseBody } from "@/lib/api";
import { toast } from "sonner";

export function useLogAnalysis() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || "";
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<LogAnalysisResponseBody | null>(null);

  async function analyzeLogs(body: LogAnalysisRequestBody) {
    setIsLoading(true);
    setError(null);
    setData(null);
    try {
      const resp = await fetch(`${apiBaseUrl}/api/v1/agent/logs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err?.detail || `HTTP ${resp.status}`);
      }
      const json: LogAnalysisResponseBody = await resp.json();
      setData(json);
      if (json.trace_id) console.log("Log Analysis Trace ID:", json.trace_id);
    } catch (err: any) {
      const msg = err?.message || "Log analysis failed";
      toast.error(msg);
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }

  return { analyzeLogs, isLoading, error, data };
}
