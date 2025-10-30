"use client";

import { useLangGraphInterrupt } from "@copilotkit/react-core";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from "@/shared/ui/dialog";
import { Button } from "@/shared/ui/button";

/**
 * Chat Interrupts for Phase 3 CopilotKit Integration
 *
 * Migrates manual interrupt queue to CopilotKit's useLangGraphInterrupt hook.
 * Handles human-in-the-loop decisions from the multi-agent workflow.
 *
 * Replaces:
 * - Manual interruptQueue state
 * - Custom interrupt dialog management
 * - Manual resolve/reject handling
 *
 * CopilotKit provides:
 * - Automatic interrupt queueing
 * - Event payload management
 * - Resolve callback handling
 */
export function ChatInterrupts() {
  useLangGraphInterrupt<{ prompt?: string }>({
    render: ({ event, resolve }) => {
      // Extract prompt text from event value
      const promptText =
        (event?.value as any)?.prompt || "This action requires your input";

      // Format event details for debugging (optional)
      const eventDetails = (() => {
        try {
          return JSON.stringify(event?.value ?? {}, null, 2);
        } catch {
          return undefined;
        }
      })();

      return (
        <Dialog open onOpenChange={() => {/* Prevent closing via backdrop */}}>
          <DialogContent hideClose>
            <DialogHeader>
              <DialogTitle>Human decision required</DialogTitle>
              <DialogDescription>{String(promptText)}</DialogDescription>
            </DialogHeader>

            {/* Show event details in development */}
            {process.env.NODE_ENV === "development" && eventDetails && (
              <pre className="mt-2 max-h-64 overflow-auto rounded-md border bg-muted/30 p-3 text-xs whitespace-pre-wrap">
                {eventDetails}
              </pre>
            )}

            <DialogFooter className="mt-4">
              <Button
                onClick={() => {
                  try {
                    resolve("reject");
                  } catch (error) {
                    console.error("Failed to reject interrupt:", error);
                  }
                }}
                variant="secondary"
              >
                Reject
              </Button>
              <Button
                onClick={() => {
                  try {
                    resolve("approve");
                  } catch (error) {
                    console.error("Failed to approve interrupt:", error);
                  }
                }}
              >
                Approve
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      );
    },
  });

  return null; // Hook only, no JSX needed
}
