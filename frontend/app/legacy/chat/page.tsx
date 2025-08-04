"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import {
  MessageCircle,
  Send,
  Loader2,
  User,
  Bot,
  Sun,
  Moon,
  Circle,
  Sparkles,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { usePrimaryAgentStream } from '@/hooks/usePrimaryAgentStream'
import { PrimaryAgentStreamEvent } from '@/lib/api'

interface Message {
  id: string
  type: "user" | "agent"
  content: string
  timestamp: Date
}

export default function PrimaryAgentPage() {
  const [isDarkMode, setIsDarkMode] = useState(true)
  const [inputValue, setInputValue] = useState("")
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      type: "agent",
      content: "Hello! I'm your Mailbird support assistant. How can I help you today?",
      timestamp: new Date(),
    },
  ])

  const { isStreaming, error, sendMessage } = usePrimaryAgentStream()

  // Listen for streaming messages
  useEffect(() => {
    const handleStreamEvent = (event: CustomEvent<PrimaryAgentStreamEvent>) => {
      const { role, content } = event.detail
      
      if (role === "assistant" && content && content !== "[DONE]") {
        const newMessage: Message = {
          id: Date.now().toString(),
          type: "agent",
          content,
          timestamp: new Date(),
        }
        setMessages(prev => [...prev, newMessage])
      }
    }

    window.addEventListener("primary-agent-stream", handleStreamEvent as EventListener)
    return () => {
      window.removeEventListener("primary-agent-stream", handleStreamEvent as EventListener)
    }
  }, [])

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isStreaming) return

    const userMessage: Message = {
      id: Date.now().toString(),
      type: "user",
      content: inputValue,
      timestamp: new Date(),
    }

    setMessages(prev => [...prev, userMessage])
    
    try {
      await sendMessage({ message: inputValue })
    } catch (error) {
      console.error("Failed to send message:", error)
    }
    
    setInputValue("")
  }

  const themeClasses = isDarkMode
    ? "bg-slate-950 text-slate-100"
    : "bg-gradient-to-br from-slate-50 via-blue-50 to-mb-blue-50 text-slate-900"

  const cardClasses = isDarkMode
    ? "bg-slate-900/40 border-slate-800/50 backdrop-blur-xl"
    : "bg-white/60 border-slate-200/50 backdrop-blur-xl shadow-sm"

  const inputClasses = isDarkMode
    ? "bg-slate-800/40 border-slate-700/50 text-slate-100 placeholder:text-slate-500 backdrop-blur-xl"
    : "bg-white/70 border-slate-300/50 text-slate-900 placeholder:text-slate-500 backdrop-blur-xl"

  return (
    <div className={cn("min-h-screen transition-all duration-700 ease-out", themeClasses)}>
      <div className="container mx-auto max-w-4xl h-screen flex flex-col">
        {/* Header */}
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-full bg-gradient-to-r from-blue-400/20 to-mb-blue-400/20">
                  <MessageCircle className="w-5 h-5 text-blue-400 animate-pulse" />
                </div>
                <h1 className="font-medium text-lg">Mailbird Support Assistant</h1>
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

        {/* Messages */}
        <div className="flex-1 px-6 overflow-hidden">
          <Card className={cn(cardClasses, "h-full")}>
            <CardContent className="p-0 h-full">
              <ScrollArea className="h-full p-4">
                <div className="space-y-4">
                  {messages.map((message) => (
                    <div
                      key={message.id}
                      className={cn(
                        "flex",
                        message.type === "user" ? "justify-end" : "justify-start"
                      )}
                    >
                      <div
                        className={cn(
                          "flex items-start gap-3 max-w-[70%]",
                          message.type === "user" ? "flex-row-reverse" : "flex-row"
                        )}
                      >
                        <div
                          className={cn(
                            "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0",
                            message.type === "user"
                              ? "bg-gradient-to-r from-blue-500 to-mb-blue-500"
                              : "bg-gradient-to-r from-green-500 to-blue-500"
                          )}
                        >
                          {message.type === "user" ? (
                            <User className="w-4 h-4 text-white" />
                          ) : (
                            <Bot className="w-4 h-4 text-white" />
                          )}
                        </div>
                        <div
                          className={cn(
                            "rounded-2xl px-4 py-3 shadow-sm",
                            message.type === "user"
                              ? isDarkMode
                                ? "bg-gradient-to-r from-blue-900/40 to-mb-blue-900/40 border border-blue-700/30"
                                : "bg-gradient-to-r from-blue-50 to-mb-blue-100/70 border border-blue-200/50"
                              : isDarkMode
                              ? "bg-gradient-to-r from-slate-800/40 to-slate-700/40 border border-slate-600/30"
                              : "bg-gradient-to-r from-slate-50 to-slate-100/70 border border-slate-200/50"
                          )}
                        >
                          <p className="text-sm leading-relaxed">{message.content}</p>
                          <p className="text-xs text-slate-500 mt-1">
                            {message.timestamp.toLocaleTimeString()}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                  {isStreaming && (
                    <div className="flex justify-start">
                      <div className="flex items-start gap-3 max-w-[70%]">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-r from-green-500 to-blue-500 flex items-center justify-center flex-shrink-0">
                          <Bot className="w-4 h-4 text-white" />
                        </div>
                        <div
                          className={cn(
                            "rounded-2xl px-4 py-3 shadow-sm",
                            isDarkMode
                              ? "bg-gradient-to-r from-slate-800/40 to-slate-700/40 border border-slate-600/30"
                              : "bg-gradient-to-r from-slate-50 to-slate-100/70 border border-slate-200/50"
                          )}
                        >
                          <div className="flex items-center gap-2">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span className="text-sm">Thinking...</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        {/* Input Area */}
        <div className="p-6">
          <div className="relative">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !isStreaming) {
                  handleSendMessage()
                }
              }}
              placeholder="Ask a question about Mailbird..."
              className={cn(
                "w-full pr-12 py-6 rounded-2xl text-sm transition-all duration-300 ease-out",
                inputClasses,
              )}
              disabled={isStreaming}
            />
            <Button
              onClick={handleSendMessage}
              disabled={isStreaming || !inputValue.trim()}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-xl bg-gradient-to-r from-blue-500 to-mb-blue-500 text-white hover:opacity-90 transition-all duration-300"
              size="sm"
            >
              {isStreaming ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </Button>
          </div>
          {error && (
            <p className="text-xs text-center mt-3 text-red-500">Error: {error}</p>
          )}
          <p className="text-xs text-center mt-3 text-slate-500 dark:text-slate-600">
            AI can make mistakes. Consider checking important information.
          </p>
        </div>
      </div>
    </div>
  )
}