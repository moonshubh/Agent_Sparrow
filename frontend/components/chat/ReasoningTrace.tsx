'use client'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { 
  Brain, 
  Target, 
  Lightbulb, 
  Shield, 
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Info
} from 'lucide-react'

interface ThinkingStep {
  phase: string
  thought: string
  confidence: number
  evidence?: string[]
  alternatives_considered?: string[]
}

interface ReasoningData {
  query_analysis?: {
    intent?: string
    problem_category?: string
    emotional_state?: string
    urgency_level?: number
    technical_complexity?: number
  }
  context_recognition?: {
    user_expertise_level?: string
    related_issues?: string[]
  }
  solution_mapping?: {
    potential_solutions?: Array<{
      solution: string
      confidence: number
      time_estimate?: string
      prerequisites?: string[]
    }>
    recommended_approach?: string
    knowledge_gaps?: string[]
  }
  tool_reasoning?: {
    decision_type?: string
    confidence?: string
    reasoning?: string
    recommended_tools?: string[]
  }
  response_strategy?: {
    approach?: string
    tone?: string
    key_points?: string[]
  }
  quality_assessment?: {
    clarity_score?: number
    completeness_score?: number
    accuracy_confidence?: number
    improvement_suggestions?: string[]
  }
  confidence_score?: number
  thinking_steps?: ThinkingStep[]
  emotional_intelligence?: {
    detected_emotion?: string
    empathy_response?: string
    emotional_validation?: number
  }
}

interface ReasoningTraceProps {
  reasoning: ReasoningData
  className?: string
}

export function ReasoningTrace({ reasoning, className = '' }: ReasoningTraceProps) {
  const getEmotionColor = (emotion?: string) => {
    switch (emotion?.toLowerCase()) {
      case 'frustrated':
      case 'anxious':
        return 'text-red-500'
      case 'confused':
        return 'text-yellow-500'
      case 'satisfied':
      case 'professional':
        return 'text-green-500'
      default:
        return 'text-gray-500'
    }
  }

  const getConfidenceColor = (confidence?: number) => {
    if (!confidence) return 'bg-gray-200'
    if (confidence >= 0.8) return 'bg-green-500'
    if (confidence >= 0.6) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  const getConfidenceLabel = (confidence?: string) => {
    switch (confidence?.toUpperCase()) {
      case 'HIGH':
        return { color: 'bg-green-100 text-green-800', icon: CheckCircle2 }
      case 'MEDIUM':
        return { color: 'bg-yellow-100 text-yellow-800', icon: Info }
      case 'LOW':
        return { color: 'bg-red-100 text-red-800', icon: XCircle }
      default:
        return { color: 'bg-gray-100 text-gray-800', icon: Info }
    }
  }

  return (
    <div className={`space-y-4 ${className}`}>
      {/* Overall Confidence */}
      {reasoning.confidence_score !== undefined && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Brain className="h-5 w-5 text-primary" />
                <CardTitle className="text-base">Reasoning Analysis</CardTitle>
              </div>
              <Badge variant="outline">
                Confidence: {(reasoning.confidence_score * 100).toFixed(0)}%
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <Progress 
              value={reasoning.confidence_score * 100} 
              className={`h-2 ${getConfidenceColor(reasoning.confidence_score)}`}
            />
          </CardContent>
        </Card>
      )}

      {/* Query Analysis */}
      {reasoning.query_analysis && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Target className="h-4 w-4 text-primary" />
              <CardTitle className="text-sm font-medium">Query Analysis</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {reasoning.query_analysis.intent && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Intent:</span>
                <span className="font-medium">{reasoning.query_analysis.intent}</span>
              </div>
            )}
            {reasoning.query_analysis.problem_category && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Category:</span>
                <Badge variant="secondary">{reasoning.query_analysis.problem_category}</Badge>
              </div>
            )}
            {reasoning.query_analysis.emotional_state && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Emotional State:</span>
                <span className={`font-medium ${getEmotionColor(reasoning.query_analysis.emotional_state)}`}>
                  {reasoning.query_analysis.emotional_state}
                </span>
              </div>
            )}
            {reasoning.query_analysis.urgency_level !== undefined && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Urgency:</span>
                <Progress value={reasoning.query_analysis.urgency_level * 100} className="w-20 h-2" />
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Solution Mapping */}
      {reasoning.solution_mapping?.potential_solutions && reasoning.solution_mapping.potential_solutions.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Lightbulb className="h-4 w-4 text-primary" />
              <CardTitle className="text-sm font-medium">Solution Candidates</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {reasoning.solution_mapping.potential_solutions.slice(0, 3).map((solution, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="flex items-start justify-between">
                    <p className="text-sm flex-1">{solution.solution}</p>
                    <Badge variant="outline" className="ml-2 text-xs">
                      {(solution.confidence * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  {solution.time_estimate && (
                    <p className="text-xs text-muted-foreground">
                      Est. time: {solution.time_estimate}
                    </p>
                  )}
                </div>
              ))}
              {reasoning.solution_mapping.knowledge_gaps && reasoning.solution_mapping.knowledge_gaps.length > 0 && (
                <div className="mt-3 pt-3 border-t">
                  <p className="text-xs text-muted-foreground">
                    Knowledge gaps identified: {reasoning.solution_mapping.knowledge_gaps.join(', ')}
                  </p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tool Reasoning */}
      {reasoning.tool_reasoning && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-primary" />
              <CardTitle className="text-sm font-medium">Tool Decision</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {reasoning.tool_reasoning.decision_type && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Decision:</span>
                <Badge variant="default">{reasoning.tool_reasoning.decision_type}</Badge>
              </div>
            )}
            {reasoning.tool_reasoning.confidence && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Confidence:</span>
                <div className="flex items-center gap-1">
                  {(() => {
                    const { color, icon: Icon } = getConfidenceLabel(reasoning.tool_reasoning.confidence)
                    return (
                      <>
                        <Icon className="h-3 w-3" />
                        <Badge className={color} variant="secondary">
                          {reasoning.tool_reasoning.confidence}
                        </Badge>
                      </>
                    )
                  })()}
                </div>
              </div>
            )}
            {reasoning.tool_reasoning.reasoning && (
              <p className="text-xs text-muted-foreground mt-2">
                {reasoning.tool_reasoning.reasoning}
              </p>
            )}
            {reasoning.tool_reasoning.recommended_tools && reasoning.tool_reasoning.recommended_tools.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {reasoning.tool_reasoning.recommended_tools.map((tool, idx) => (
                  <Badge key={idx} variant="outline" className="text-xs">
                    {tool}
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Thinking Steps */}
      {reasoning.thinking_steps && reasoning.thinking_steps.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Reasoning Process</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {reasoning.thinking_steps.map((step, idx) => (
                <div key={idx} className="space-y-1">
                  <div className="flex items-start gap-2">
                    <Badge variant="outline" className="text-xs shrink-0">
                      {step.phase}
                    </Badge>
                    <p className="text-sm text-muted-foreground">{step.thought}</p>
                  </div>
                  {step.confidence > 0 && (
                    <div className="ml-14">
                      <Progress value={step.confidence * 100} className="h-1" />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Quality Assessment */}
      {reasoning.quality_assessment && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Quality Assessment</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {reasoning.quality_assessment.clarity_score !== undefined && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Clarity:</span>
                  <Progress value={reasoning.quality_assessment.clarity_score * 100} className="w-20 h-2" />
                </div>
              )}
              {reasoning.quality_assessment.completeness_score !== undefined && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Completeness:</span>
                  <Progress value={reasoning.quality_assessment.completeness_score * 100} className="w-20 h-2" />
                </div>
              )}
              {reasoning.quality_assessment.accuracy_confidence !== undefined && (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Accuracy:</span>
                  <Progress value={reasoning.quality_assessment.accuracy_confidence * 100} className="w-20 h-2" />
                </div>
              )}
              {reasoning.quality_assessment.improvement_suggestions && reasoning.quality_assessment.improvement_suggestions.length > 0 && (
                <div className="mt-3 pt-3 border-t">
                  <p className="text-xs font-medium mb-1">Improvement Areas:</p>
                  <ul className="text-xs text-muted-foreground space-y-1">
                    {reasoning.quality_assessment.improvement_suggestions.map((suggestion, idx) => (
                      <li key={idx} className="flex items-start gap-1">
                        <AlertTriangle className="h-3 w-3 mt-0.5 text-yellow-500 shrink-0" />
                        <span>{suggestion}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Emotional Intelligence */}
      {reasoning.emotional_intelligence && reasoning.emotional_intelligence.detected_emotion && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">Emotional Intelligence</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Detected Emotion:</span>
              <span className={`font-medium ${getEmotionColor(reasoning.emotional_intelligence.detected_emotion)}`}>
                {reasoning.emotional_intelligence.detected_emotion}
              </span>
            </div>
            {reasoning.emotional_intelligence.empathy_response && (
              <p className="text-sm text-muted-foreground mt-2">
                "{reasoning.emotional_intelligence.empathy_response}"
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}