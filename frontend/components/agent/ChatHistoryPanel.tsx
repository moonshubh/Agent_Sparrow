"use client"

import React from 'react';
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { cn } from "@/lib/utils"
import {
  History,
  ChevronLeft,
  ChevronRight,
  Download,
} from "lucide-react";
import { ChatMessage } from "@/lib/api";
import Message from "./Message";



interface ChatHistoryPanelProps {
  isChatHistoryOpen: boolean
  setIsChatHistoryOpen: (isOpen: boolean) => void
  chatHistory: ChatMessage[]
  handleFeedback: (messageId: string, feedback: "positive" | "negative") => void
  exportToMarkdown: () => void
  getAgentIcon: (agentType: string) => React.ReactNode
  panelClasses: string
  isDarkMode: boolean
}

export default function ChatHistoryPanel({
  isChatHistoryOpen,
  setIsChatHistoryOpen,
  chatHistory,
  handleFeedback,
  exportToMarkdown,
  getAgentIcon,
  panelClasses,
  isDarkMode,
}: ChatHistoryPanelProps) {
  return (
    <div
      className={cn(
        "transition-all duration-500 ease-out",
        panelClasses,
        isChatHistoryOpen ? "w-80 border-r" : "w-12",
      )}
    >
      <div className="h-full flex flex-col">
        {/* Panel Header */}
        <div className="p-6">
          <div className="flex items-center justify-between">
            {isChatHistoryOpen && (
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-full bg-gradient-to-r from-purple-400/20 to-pink-400/20">
                  <History className="w-4 h-4 text-purple-400" />
                </div>
                <span className="font-medium text-sm">Chat History</span>
              </div>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsChatHistoryOpen(!isChatHistoryOpen)}
              className="p-2 h-8 w-8 rounded-full hover:bg-slate-200/50 dark:hover:bg-slate-700/50 transition-all duration-300"
            >
              {isChatHistoryOpen ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </Button>
          </div>
        </div>

        {/* Chat History Content */}
        {isChatHistoryOpen && (
          <ScrollArea className="flex-1 px-6">
            <div className="space-y-6 pb-6">
              {chatHistory.map((message, index) => (
                <div key={message.id} className="space-y-3">
                  {/* Floating timestamp */}
                  {(index === 0 ||
                    new Date(message.timestamp).toDateString() !==
                      new Date(chatHistory[index - 1].timestamp).toDateString()) && (
                    <div className="flex justify-center">
                      <div className="px-3 py-1 rounded-full bg-slate-200/50 dark:bg-slate-700/50 text-xs text-slate-600 dark:text-slate-400">
                        {message.timestamp.toLocaleDateString()}
                      </div>
                    </div>
                  )}

                  <Message
                    message={message}
                    isDarkMode={isDarkMode}
                    handleFeedback={handleFeedback}
                    getAgentIcon={getAgentIcon}
                  />
                </div>
              ))}
            </div>
          </ScrollArea>
        )}

        {/* Export Button */}
        {isChatHistoryOpen && (
          <div className="p-6">
            <Button
              variant="outline"
              size="sm"
              onClick={exportToMarkdown}
              className="w-full text-xs rounded-xl bg-gradient-to-r from-purple-500/10 to-pink-500/10 border-purple-300/30 hover:from-purple-500/20 hover:to-pink-500/20 transition-all duration-300"
            >
              <Download className="w-3 h-3 mr-2" />
              Export History
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
