"use client";

import { useState } from 'react';
import { ChatMessage, ResearchStep, ApiError } from '@/services/api/api';

const initialChatHistory: ChatMessage[] = [
  {
    id: "1",
    type: "user",
    content: "What is the latest Google Gemini Model?",
    timestamp: new Date(Date.now() - 300000),
  },
  {
    id: "2",
    type: "agent",
    content:
      "Based on my research, the latest Google Gemini models are Gemini 2.5 Pro and Gemini 2.5 Flash, released in May 2025. These models feature enhanced reasoning capabilities and improved performance benchmarks.",
    timestamp: new Date(Date.now() - 240000),
    agentType: "research",
    feedback: null,
  },
  {
    id: "3",
    type: "user",
    content: "Can you analyze the performance differences between these models?",
    timestamp: new Date(Date.now() - 180000),
  },
  {
    id: "4",
    type: "agent",
    content:
      "Gemini 2.5 Flash is optimized for speed and efficiency, while Gemini 2.5 Pro offers enhanced reasoning and complex task handling. Flash processes queries 40% faster, while Pro shows 25% better accuracy on complex reasoning tasks.",
    timestamp: new Date(Date.now() - 120000),
    agentType: "research",
    feedback: "positive",
  },
];

export const useResearchAgent = () => {
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>(initialChatHistory);
  const [currentResearchSteps, setCurrentResearchSteps] = useState<ResearchStep[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<ApiError | null>(null);

  const sendQuery = async (prompt: string) => {
    setIsLoading(true);
    setError(null);
    setCurrentResearchSteps([]);

    const newId = (chatHistory.length + 1).toString();
    const userMessage: ChatMessage = {
      id: newId,
      type: 'user',
      content: prompt,
      timestamp: new Date(),
    };
    setChatHistory(prev => [...prev, userMessage]);

    try {
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || "";
      const response = await fetch(`${apiBaseUrl}/api/v1/agent/research/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query: prompt }),
      });

      if (!response.body) {
        throw new Error('No response body');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n\n').filter(line => line.startsWith('data:'));

        for (const line of lines) {
          const json = line.replace('data: ', '');
          const event = JSON.parse(json);

          if (event.type === 'step') {
            setCurrentResearchSteps(prev => [...prev, event.data]);
          } else if (event.type === 'message') {
            setChatHistory(prev => [...prev, event.data]);
          }
        }
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to contact research agent';
      setError({ detail: message });
    } finally {
      setIsLoading(false);
    }
  };

  const handleFeedback = (messageId: string, feedback: 'positive' | 'negative') => {
    setChatHistory(prev =>
      prev.map(msg =>
        msg.id === messageId ? { ...msg, feedback } : msg
      )
    );
  };

  const exportToMarkdown = () => {
    let markdownContent = "# Chat History\n\n";
    chatHistory.forEach((message) => {
      const sender = message.type === "user" ? "**User**" : `**Agent (${message.agentType})**`;
      markdownContent += `${sender}: ${message.content}\n\n`;
    });

    markdownContent += "\n### Research Steps\n\n";
    currentResearchSteps.forEach((step) => {
      markdownContent += `- **${step.type}**: ${step.description} (${step.status})\n`;
    });

    const blob = new Blob([markdownContent], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "chat-history.md";
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  };

  return {
    chatHistory,
    currentResearchSteps,
    isLoading,
    error,
    sendQuery,
    handleFeedback,
    exportToMarkdown,
  };
};
