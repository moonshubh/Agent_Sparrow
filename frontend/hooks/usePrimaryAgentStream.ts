import { useState, useCallback } from "react";
import { PrimaryAgentChatRequestBody, PrimaryAgentStreamEvent } from "@/lib/api";
import { toast } from "sonner";
import { ChatMessage } from "@/types/chat";

interface UsePrimaryAgentStreamReturn {
  isStreaming: boolean;
  error: string | null;
  sendMessage: (body: PrimaryAgentChatRequestBody, messages?: ChatMessage[], sessionId?: string) => Promise<void>;
}

/**
 * React hook to handle streaming chat with the Primary Support Agent.
 * Wraps the /api/v1/agent/chat/stream endpoint and emits SSE chunks.
 */
export function usePrimaryAgentStream(): UsePrimaryAgentStreamReturn {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || "";
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(async (body: PrimaryAgentChatRequestBody, messages?: ChatMessage[], sessionId?: string) => {
    setIsStreaming(true);
    setError(null);
    try {
      // Build request body, only including session_id if defined
      const requestBody: any = {
        ...body,
        messages: messages || []
      };
      
      // Only add session_id if it's defined to avoid sending undefined
      if (sessionId !== undefined) {
        requestBody.session_id = sessionId;
      }
      
      const resp = await fetch(`${apiBaseUrl}/api/v1/agent/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
      });

      const traceId = resp.headers.get("x-trace-id");
      if (traceId) {
        console.log("Primary Agent Stream Trace ID:", traceId);
      }

      if (!resp.ok || !resp.body) {
        const errDetail = await resp.text();
        throw new Error(errDetail || `HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let done = false;

      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        if (value) {
          const chunkText = decoder.decode(value, { stream: true });
          const lines = chunkText.split("\n").filter(Boolean);
          for (const line of lines) {
            if (line.startsWith("data:")) {
              const jsonStr = line.replace("data:", "").trim();
              if (jsonStr === "[DONE]") {
                done = true;
                break;
              }
              try {
                const event: PrimaryAgentStreamEvent = JSON.parse(jsonStr);
                window.dispatchEvent(new CustomEvent("primary-agent-stream", { detail: event }));
              } catch (_) {
                // silently ignore JSON parse errors for malformed chunks
              }
            }
          }
        }
      }
    } catch (err: any) {
      const msg = err?.message || "Primary agent stream error";
      toast.error(msg);
      setError(msg);
    } finally {
      setIsStreaming(false);
    }
  }, [apiBaseUrl]);

  return { isStreaming, error, sendMessage };
}
