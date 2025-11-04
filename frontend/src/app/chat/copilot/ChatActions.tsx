"use client";

import { useCopilotAction, useCopilotChat } from "@copilotkit/react-core";
import { FeedbackDialog } from "@/features/global-knowledge/components/FeedbackDialog";
import { CorrectionDialog } from "@/features/global-knowledge/components/CorrectionDialog";
import { useState } from "react";

/**
 * Chat Actions for Phase 3 CopilotKit Integration
 *
 * Migrates legacy slash commands to CopilotKit actions:
 * - /feedback → submitFeedback action
 * - /correct → submitCorrection action
 *
 * Users can trigger these via natural language:
 * - "I want to submit feedback about that response"
 * - "I need to correct something you said"
 *
 * CopilotKit will automatically map the intent to the action.
 */
export function ChatActions({
  sessionId,
  agentType,
}: {
  sessionId?: string;
  agentType: "primary" | "log_analysis";
}) {
  const chat = useCopilotChat({})
  // Feedback dialog state
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [feedbackSelected, setFeedbackSelected] = useState("");

  // Correction dialog state
  const [correctionOpen, setCorrectionOpen] = useState(false);
  const [incorrectText, setIncorrectText] = useState("");
  const [correctedText, setCorrectedText] = useState("");

  // Action: Submit Feedback
  useCopilotAction({
    name: "submitFeedback",
    description:
      "Submit feedback about the AI assistant's response. Use this when the user wants to provide feedback, report issues, or share thoughts about the assistant's performance.",
    parameters: [
      {
        name: "feedback",
        type: "string",
        description: "The feedback text from the user",
        required: true,
      },
      {
        name: "selectedText",
        type: "string",
        description:
          "Optional context or selected text the feedback refers to",
        required: false,
      },
    ],
    handler: async ({ feedback, selectedText }) => {
      setFeedbackText(feedback || "");
      setFeedbackSelected(selectedText || "");
      setFeedbackOpen(true);
      return {
        success: true,
        message: "Feedback dialog opened. Please complete the form.",
      };
    },
  });

  // Action: Submit Correction
  useCopilotAction({
    name: "submitCorrection",
    description:
      "Submit a correction for incorrect information provided by the AI assistant. Use this when the user identifies misinformation or wants to correct the assistant's response.",
    parameters: [
      {
        name: "incorrectText",
        type: "string",
        description: "The incorrect information that needs correction",
        required: true,
      },
      {
        name: "correctedText",
        type: "string",
        description: "The correct information",
        required: true,
      },
    ],
    handler: async ({ incorrectText, correctedText }) => {
      setIncorrectText(incorrectText || "");
      setCorrectedText(correctedText || "");
      setCorrectionOpen(true);
      return {
        success: true,
        message: "Correction dialog opened. Please complete the form.",
      };
    },
  });

  // Phase 5: Minimal visibility actions for key tools/flows
  useCopilotAction({
    name: "knowledge_search",
    description: "Search Mailbird knowledge base",
    parameters: [
      { name: "query", type: "string", description: "What to search for", required: false },
    ],
    handler: async ({ query }: { query?: string }) => {
      const text = query && String(query).trim().length ? String(query) : "Search knowledge base for …"
      try { chat?.setInput?.(text) } catch {}
      return { ok: true }
    },
  })

  useCopilotAction({
    name: "web_search",
    description: "Perform a quick web search",
    parameters: [
      { name: "query", type: "string", description: "Topic to research", required: false },
    ],
    handler: async ({ query }: { query?: string }) => {
      const text = query && String(query).trim().length ? String(query) : "Research on the web: …"
      try { chat?.setInput?.(text) } catch {}
      return { ok: true }
    },
  })

  useCopilotAction({
    name: "analyze_logs",
    description: "Analyze attached logs for issues and patterns",
    parameters: [
      { name: "hint", type: "string", description: "Optional hint or focus area", required: false },
    ],
    handler: async ({ hint }: { hint?: string }) => {
      const text = hint && String(hint).trim().length ? String(hint) : "Analyze the attached logs and summarize issues."
      try { chat?.setInput?.(text) } catch {}
      return { ok: true }
    },
  })

  return (
    <>
      {/* Feedback Dialog */}
      <FeedbackDialog
        open={feedbackOpen}
        initialFeedback={feedbackText}
        selectedText={feedbackSelected}
        sessionId={sessionId || null}
        agent={agentType}
        onClose={() => setFeedbackOpen(false)}
      />

      {/* Correction Dialog */}
      <CorrectionDialog
        open={correctionOpen}
        initialIncorrect={incorrectText}
        initialCorrected={correctedText}
        sessionId={sessionId || null}
        agent={agentType}
        onClose={() => setCorrectionOpen(false)}
      />
    </>
  );
}
