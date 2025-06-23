"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button";
import ChatHistoryPanel from "@/components/agent/ChatHistoryPanel";
import ResearchPanel from "@/components/agent/ResearchPanel";
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  ChevronUp,
  ChevronDown,
  FileText,
  Search,
  RotateCcw,
  Loader2,
  Zap,
  Edit3,
  Download,
  FileDown,
  Paperclip,
  User,
  FileSearch,
  Brain,
  ThumbsUp,
  ThumbsDown,
  Sun,
  Moon,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  History,
  Circle,
} from "lucide-react"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils";
import { useResearchAgent } from '@/hooks/useResearchAgent';



export default function Component() {
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [isResearchExpanded, setIsResearchExpanded] = useState(true);
  const [isChatHistoryOpen, setIsChatHistoryOpen] = useState(true);
  const [inputValue, setInputValue] = useState("Who won the Euro 2024 and scored the most goals?");
  const [selectedAgent, setSelectedAgent] = useState("research");

  const {
    chatHistory,
    currentResearchSteps,
    isLoading,
    error,
    sendQuery,
    handleFeedback,
    exportToMarkdown,
  } = useResearchAgent();

  const getAgentIcon = (agentType: string) => {
    switch (agentType) {
      case "general":
        return <User className="w-3 h-3 text-blue-400" />
      case "log-analysis":
        return <FileSearch className="w-3 h-3 text-green-400" />
      case "research":
        return <Search className="w-3 h-3 text-purple-400" />
      default:
        return <Brain className="w-3 h-3 text-gray-400" />
    }
  }

  const themeClasses = isDarkMode
    ? "bg-slate-950 text-slate-100"
    : "bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 text-slate-900"

  const cardClasses = isDarkMode
    ? "bg-slate-900/40 border-slate-800/50 backdrop-blur-xl"
    : "bg-white/60 border-slate-200/50 backdrop-blur-xl shadow-sm"

  const inputClasses = isDarkMode
    ? "bg-slate-800/40 border-slate-700/50 text-slate-100 placeholder:text-slate-500 backdrop-blur-xl"
    : "bg-white/70 border-slate-300/50 text-slate-900 placeholder:text-slate-500 backdrop-blur-xl"

  const panelClasses = isDarkMode
    ? "bg-slate-900/30 backdrop-blur-xl border-slate-800/30"
    : "bg-white/40 backdrop-blur-xl border-slate-200/30"

  return (
    <div className={cn("min-h-screen transition-all duration-700 ease-out", themeClasses)}>
      <div className="flex h-screen">
        <ChatHistoryPanel
          isChatHistoryOpen={isChatHistoryOpen}
          setIsChatHistoryOpen={setIsChatHistoryOpen}
          chatHistory={chatHistory}
          handleFeedback={handleFeedback}
          exportToMarkdown={exportToMarkdown}
          getAgentIcon={getAgentIcon}
          panelClasses={panelClasses}
          isDarkMode={isDarkMode}
        />

        {/* Main Content */}
        <div className="flex-1 flex flex-col">
          {/* Header */}
          <div className="p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-full bg-gradient-to-r from-purple-400/20 to-pink-400/20">
                    <Sparkles className="w-5 h-5 text-purple-400 animate-pulse" />
                  </div>
                  <h1 className="font-medium text-lg">AI Research Assistant</h1>
                </div>
                <div className="flex items-center gap-1">
                  <Circle className="w-2 h-2 fill-green-400 text-green-400 animate-pulse" />
                  <span className="text-xs text-slate-500 dark:text-slate-400">Online</span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setIsDarkMode(!isDarkMode)}
                  className="p-2 rounded-full hover:bg-slate-200/50 dark:hover:bg-slate-700/50 transition-all duration-300"
                >
                  {isDarkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
                </Button>
              </div>
            </div>
          </div>

          {/* Main Chat Area */}
          <div className="flex-1 px-6 overflow-auto">
            <div className="max-w-4xl mx-auto space-y-8">
              {/* User Message */}
              <div className="flex justify-end">
                <div
                  className={cn(
                    "rounded-2xl px-5 py-4 max-w-md shadow-sm transition-all duration-300 hover:scale-[1.02]",
                    isDarkMode
                      ? "bg-gradient-to-r from-blue-900/40 to-blue-800/40 border border-blue-700/30"
                      : "bg-gradient-to-r from-blue-50 to-blue-100/70 border border-blue-200/50",
                  )}
                >
                  <p className="text-sm leading-relaxed">What is the latest Google Gemini Model?</p>
                </div>
              </div>

              {/* Research Section */}
              <ResearchPanel
                isResearchExpanded={isResearchExpanded}
                setIsResearchExpanded={setIsResearchExpanded}
                currentResearchSteps={currentResearchSteps}
                cardClasses={cardClasses}
              />

              {/* Agent Response */}
              <div className="flex justify-start">
                <div
                  className={cn(
                    "rounded-2xl px-5 py-4 max-w-md shadow-sm transition-all duration-300 hover:scale-[1.02]",
                    isDarkMode
                      ? "bg-gradient-to-r from-slate-800/40 to-slate-700/40 border border-slate-600/30"
                      : "bg-gradient-to-r from-slate-50 to-slate-100/70 border border-slate-200/50",
                  )}
                >
                  <p className="text-sm leading-relaxed">
                    Based on my research, the latest Google Gemini models are Gemini 2.5 Pro and Gemini 2.5 Flash,
                    released in May 2025. These models feature enhanced reasoning capabilities and improved
                    performance benchmarks.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Input Area */}
          <div className="p-6">
            <div className="max-w-4xl mx-auto">
              <div className="relative">
                <Input
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !isLoading) {
                      sendQuery(inputValue);
                      setInputValue('');
                    }
                  }}
                  placeholder="Ask a question or type a command..."
                  className={cn(
                    "w-full pl-12 pr-32 py-6 rounded-2xl text-sm transition-all duration-300 ease-out",
                    inputClasses,
                  )}
                  disabled={isLoading}
                />
                <div className="absolute left-4 top-1/2 -translate-y-1/2">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="p-2 rounded-full hover:bg-slate-200/50 dark:hover:bg-slate-700/50 transition-all duration-300"
                      >
                        {getAgentIcon(selectedAgent)}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent>
                      <DropdownMenuItem onClick={() => setSelectedAgent("general")}>General</DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setSelectedAgent("log-analysis")}>Log Analysis</DropdownMenuItem>
                      <DropdownMenuItem onClick={() => setSelectedAgent("research")}>Research</DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
                <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="p-2 rounded-full hover:bg-slate-200/50 dark:hover:bg-slate-700/50 transition-all duration-300"
                  >
                    <Paperclip className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="default"
                    className="rounded-xl bg-gradient-to-r from-purple-500 to-pink-500 text-white hover:opacity-90 transition-all duration-300"
                    onClick={() => {
                      sendQuery(inputValue);
                      setInputValue('');
                    }}
                    disabled={isLoading}
                  >
                    {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Send'}
                  </Button>
                </div>
              </div>
              <p className="text-xs text-center mt-3 text-slate-500 dark:text-slate-600">
                {error ? (
                  <span className="text-red-500">Error: {error.detail}</span>
                ) : (
                  "AI can make mistakes. Consider checking important information."
                )}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
