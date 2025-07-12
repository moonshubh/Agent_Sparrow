"use client"

import React from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  Search,
  ChevronUp,
  ChevronDown,
  ThumbsUp,
  ThumbsDown,
  Zap,
  Loader2,
} from "lucide-react";
import { ResearchStep } from "@/lib/api";



interface ResearchPanelProps {
  isResearchExpanded: boolean;
  setIsResearchExpanded: (isExpanded: boolean) => void;
  currentResearchSteps: ResearchStep[];
  cardClasses: string;
}

export default function ResearchPanel({
  isResearchExpanded,
  setIsResearchExpanded,
  currentResearchSteps,
  cardClasses,
}: ResearchPanelProps) {
  return (
    <Card className={cn(cardClasses, "transition-all duration-300 hover:shadow-lg")}>
      <CardContent className="p-8">
        {/* Research Header */}
        <div className="flex items-center justify-between mb-8">
          <button
            onClick={() => setIsResearchExpanded(!isResearchExpanded)}
            className="flex items-center gap-3 hover:opacity-70 transition-all duration-300"
          >
            <div className="p-2 rounded-full bg-gradient-to-r from-mb-blue-400/20 to-pink-400/20">
              <Search className="w-4 h-4 text-mb-blue-400" />
            </div>
            <span className="font-medium">Research</span>
            {isResearchExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          <div className="flex items-center gap-3">
            {/* Feedback buttons for current research */}
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 rounded-full hover:text-green-500 hover:bg-green-500/10 transition-all duration-300"
            >
              <ThumbsUp className="w-4 h-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 rounded-full hover:text-red-500 hover:bg-red-500/10 transition-all duration-300"
            >
              <ThumbsDown className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Research Steps - Collapsible */}
        {isResearchExpanded && (
          <div className="space-y-6">
            {currentResearchSteps.map((step, index) => (
              <div key={index} className="flex items-start gap-4">
                <div className="flex flex-col items-center">
                  <div
                    className={cn(
                      "w-6 h-6 rounded-full flex items-center justify-center",
                      step.status === "completed" ? "bg-green-500/20" : "bg-slate-500/20",
                    )}
                  >
                    {step.status === "completed" ? (
                      <Zap className="w-3 h-3 text-green-500" />
                    ) : (
                      <Loader2 className="w-3 h-3 text-slate-500 animate-spin" />
                    )}
                  </div>
                  {index < currentResearchSteps.length - 1 && (
                    <div className="w-px h-8 bg-slate-300/30 dark:bg-slate-700/30" />
                  )}
                </div>
                <div>
                  <p className="font-medium text-sm">{step.type}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{step.description}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
