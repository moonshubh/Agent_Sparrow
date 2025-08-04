"use client"

import React from 'react';
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  User,
  ThumbsUp,
  ThumbsDown,
} from "lucide-react";
import { ChatMessage } from "@/lib/api";



interface MessageProps {
  message: ChatMessage;
  isDarkMode: boolean;
  handleFeedback: (messageId: string, feedback: "positive" | "negative") => void;
  getAgentIcon: (agentType: string) => React.ReactNode;
}

export default function Message({ message, isDarkMode, handleFeedback, getAgentIcon }: MessageProps) {
  return (
    <div
      className={cn(
        "p-4 rounded-2xl text-sm transition-all duration-300 hover:scale-[1.02]",
        message.type === "user"
          ? isDarkMode
            ? "bg-gradient-to-r from-blue-900/40 to-blue-800/40 border border-blue-700/30 ml-4"
            : "bg-gradient-to-r from-blue-50 to-blue-100/70 border border-blue-200/50 ml-4"
          : isDarkMode
            ? "bg-gradient-to-r from-slate-800/40 to-slate-700/40 border border-slate-600/30 mr-4"
            : "bg-gradient-to-r from-slate-50 to-slate-100/70 border border-slate-200/50 mr-4",
      )}
    >
      <div className="flex items-center gap-2 mb-3">
        {message.type === "user" ? (
          <div className="p-1 rounded-full bg-blue-400/20">
            <User className="w-3 h-3 text-blue-400" />
          </div>
        ) : (
          <div className="p-1 rounded-full bg-mb-blue-400/20">
            {getAgentIcon(message.agentType || "general")}
          </div>
        )}
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {message.timestamp.toLocaleTimeString()}
        </span>
      </div>
      <p className="text-xs leading-relaxed mb-3">{message.content}</p>

      {/* Feedback buttons for agent messages */}
      {message.type === "agent" && (
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              "h-6 w-6 p-0 rounded-full transition-all duration-300",
              message.feedback === "positive"
                ? "text-green-500 bg-green-500/20"
                : "hover:text-green-500 hover:bg-green-500/10",
            )}
            onClick={() => handleFeedback(message.id, "positive")}
          >
            <ThumbsUp className="w-3 h-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              "h-6 w-6 p-0 rounded-full transition-all duration-300",
              message.feedback === "negative"
                ? "text-red-500 bg-red-500/20"
                : "hover:text-red-500 hover:bg-red-500/10",
            )}
            onClick={() => handleFeedback(message.id, "negative")}
          >
            <ThumbsDown className="w-3 h-3" />
          </Button>
        </div>
      )}
    </div>
  );
}
