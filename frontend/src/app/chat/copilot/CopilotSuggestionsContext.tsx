"use client";

import React, { createContext, useContext } from "react";
import type { Suggestion } from "@/features/chat/hooks/useCopilotSuggestions";

interface CopilotSuggestionsContextValue {
  suggestions: Suggestion[];
  isGenerating: boolean;
  onSuggestionSelected?: (suggestion: Suggestion, options?: { sendImmediately?: boolean }) => void;
  clearSuggestions?: () => void;
}

const CopilotSuggestionsContext = createContext<CopilotSuggestionsContextValue>({
  suggestions: [],
  isGenerating: false,
});

function useCopilotSuggestionsContext() {
  return useContext(CopilotSuggestionsContext);
}

export { CopilotSuggestionsContext, useCopilotSuggestionsContext };
