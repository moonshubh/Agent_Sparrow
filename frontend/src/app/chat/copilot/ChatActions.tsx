"use client";

import { useCopilotAction } from "@copilotkit/react-core";
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
