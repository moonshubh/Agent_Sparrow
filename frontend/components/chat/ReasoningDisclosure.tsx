"use client"

import React from "react"
import { Info } from "lucide-react"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

// Types for reasoning UI
export interface UIDecisionStep {
  label: string
  action: string
  evidence?: string
}

export interface UIReasoning {
  summary: string
  decision_path: UIDecisionStep[]
  assumptions: string[]
  confidence: number
  flags: (
    | "downgraded_model"
    | "missing_info"
    | "tool_used"
    | "kb_consulted"
    | "limited_budget"
    | "processing_error"
    | "parsing_error"
  )[]
}

interface ReasoningDisclosureProps {
  reasoning?: UIReasoning
  className?: string
}

export function ReasoningDisclosure({
  reasoning,
  className,
}: ReasoningDisclosureProps) {
  if (!reasoning) return null

  const confidenceColor = 
    reasoning.confidence >= 0.8 ? "text-green-600 dark:text-green-400" :
    reasoning.confidence >= 0.6 ? "text-yellow-600 dark:text-yellow-400" :
    "text-red-600 dark:text-red-400"

  const flagVariants: Record<string, { variant: "default" | "secondary" | "destructive" | "outline", label: string }> = {
    downgraded_model: { variant: "secondary", label: "Model downgraded" },
    missing_info: { variant: "outline", label: "Missing information" },
    tool_used: { variant: "default", label: "Tools used" },
    kb_consulted: { variant: "default", label: "Knowledge base consulted" },
    limited_budget: { variant: "secondary", label: "Free-tier optimized" },
    processing_error: { variant: "destructive", label: "Processing error" },
    parsing_error: { variant: "destructive", label: "Parsing error" },
  }

  return (
    <Accordion
      type="single"
      collapsible
      className={cn("mt-4 border rounded-lg", className)}
    >
      <AccordionItem value="reasoning" className="border-none">
        <AccordionTrigger className="px-4 py-3 hover:no-underline hover:bg-accent/50 rounded-t-lg">
          <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
            <Info className="w-4 h-4" />
            Why this answer?
          </span>
        </AccordionTrigger>
        <AccordionContent className="px-4 pb-4 pt-2">
          {/* Summary */}
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <p className="text-muted-foreground">{reasoning.summary}</p>
          </div>

          {/* Decision Path */}
          {reasoning.decision_path.length > 0 && (
            <div className="mt-4">
              <h4 className="text-xs font-medium uppercase text-muted-foreground mb-2">
                Decision Steps
              </h4>
              <ol className="list-decimal list-inside space-y-2">
                {reasoning.decision_path.map((step, index) => (
                  <li key={index} className="text-sm">
                    <span className="font-medium">{step.label}:</span>{" "}
                    <span className="text-muted-foreground">{step.action}</span>
                    {step.evidence && (
                      <div className="ml-6 mt-1 text-xs text-muted-foreground/70">
                        Evidence: {step.evidence}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Assumptions */}
          {reasoning.assumptions.length > 0 && (
            <div className="mt-4">
              <h4 className="text-xs font-medium uppercase text-muted-foreground mb-2">
                Assumptions
              </h4>
              <ul className="list-disc list-inside space-y-1">
                {reasoning.assumptions.map((assumption, index) => (
                  <li key={index} className="text-sm text-muted-foreground">
                    {assumption}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Confidence and Flags */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className={cn("text-xs", confidenceColor)}>
              Confidence: {(reasoning.confidence * 100).toFixed(0)}%
            </Badge>
            
            {reasoning.flags.map((flag) => {
              const config = flagVariants[flag] || { variant: "outline" as const, label: flag }
              return (
                <Badge key={flag} variant={config.variant} className="text-xs">
                  {config.label}
                </Badge>
              )
            })}
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}