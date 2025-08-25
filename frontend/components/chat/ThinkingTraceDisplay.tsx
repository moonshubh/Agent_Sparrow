'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Brain, Zap, AlertTriangle, CheckCircle } from 'lucide-react';
import type { ThinkingTrace, ConfidenceScore, ConfidenceLevel } from '@/types/chat';

interface ThinkingTraceDisplayProps {
  trace: ThinkingTrace | null;
  className?: string;
}

/**
 * Get confidence level from numeric score
 */
function getConfidenceLevel(confidence: ConfidenceScore): 'high' | 'med' | 'low' {
  if (confidence >= 0.8) return 'high';
  if (confidence >= 0.6) return 'med';
  return 'low';
}

/**
 * Get text color class for confidence level
 */
function getConfidenceColor(confidence: ConfidenceScore): string {
  const level = getConfidenceLevel(confidence);
  switch (level) {
    case 'high': return 'text-green-600';
    case 'med': return 'text-yellow-600';
    case 'low': return 'text-red-600';
  }
}

/**
 * Get background color class for confidence level
 */
function getConfidenceBg(confidence: ConfidenceScore): string {
  const level = getConfidenceLevel(confidence);
  switch (level) {
    case 'high': return 'bg-green-50';
    case 'med': return 'bg-yellow-50';
    case 'low': return 'bg-red-50';
  }
}

/**
 * Mapping of confidence levels to numeric scores
 */
const CONFIDENCE_LEVEL_SCORES: Record<ConfidenceLevel, ConfidenceScore> = {
  'HIGH': 0.9,
  'MEDIUM': 0.6,
  'LOW': 0.3
} as const;

/**
 * Convert confidence level string to numeric score for display
 */
function confidenceLevelToScore(level: ConfidenceLevel): ConfidenceScore {
  return CONFIDENCE_LEVEL_SCORES[level];
}

export const ThinkingTraceDisplay: React.FC<ThinkingTraceDisplayProps> = ({ 
  trace, 
  className = '' 
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!trace) return null;

  return (
    <div className={`thinking-trace-container mt-2 ${className}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 text-xs text-gray-600 hover:text-gray-800 transition-colors p-2 rounded hover:bg-gray-50 w-full text-left"
      >
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Brain size={14} className="text-blue-500" />
        <span className="font-medium">Thinking Trace</span>
        <span className={`ml-auto font-semibold ${getConfidenceColor(trace.confidence)}`}>
          {Math.round(trace.confidence * 100)}% confident
        </span>
      </button>

      {isExpanded && (
        <div className="mt-2 p-3 bg-gray-50 rounded-lg space-y-3 text-xs">
          {/* Query Analysis */}
          {(trace.emotional_state || trace.problem_category || trace.complexity) && (
            <div className="space-y-1">
              <h4 className="font-semibold text-gray-700 flex items-center gap-1">
                <Zap size={12} />
                Query Analysis
              </h4>
              <div className="pl-4 space-y-0.5 text-gray-600">
                {trace.emotional_state && (
                  <div>Emotion: <span className="font-medium">{trace.emotional_state}</span></div>
                )}
                {trace.problem_category && (
                  <div>Category: <span className="font-medium">{trace.problem_category}</span></div>
                )}
                {trace.complexity && (
                  <div>Complexity: <span className="font-medium">{trace.complexity}</span></div>
                )}
              </div>
            </div>
          )}

          {/* Tool Decision */}
          {trace.tool_decision && (
            <div className="flex items-center gap-2 p-2 bg-white rounded">
              <span className="text-gray-500">Tool Decision:</span>
              <span className="font-medium">{trace.tool_decision}</span>
              {trace.tool_confidence && (
                <span className={`ml-auto text-xs ${getConfidenceColor(
                  confidenceLevelToScore(trace.tool_confidence)
                )}`}>
                  {trace.tool_confidence}
                </span>
              )}
            </div>
          )}

          {/* Thinking Steps */}
          {trace.thinking_steps && trace.thinking_steps.length > 0 && (
            <div className="space-y-1">
              <h4 className="font-semibold text-gray-700">Reasoning Steps:</h4>
              <div className="space-y-1">
                {trace.thinking_steps.map((step) => (
                  <div 
                    key={step.phase} 
                    className={`flex items-start gap-2 p-2 rounded ${getConfidenceBg(step.confidence)}`}
                  >
                    <span className="text-blue-500 mt-0.5">→</span>
                    <div className="flex-1">
                      <div className="font-medium text-gray-700">{step.phase}</div>
                      <div className="text-gray-600">{step.thought}</div>
                    </div>
                    <span className={`text-xs ${getConfidenceColor(step.confidence)}`}>
                      {Math.round(step.confidence * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Knowledge Gaps */}
          {trace.knowledge_gaps && trace.knowledge_gaps.length > 0 && (
            <div className="p-2 bg-yellow-50 rounded">
              <div className="flex items-center gap-1 text-yellow-700">
                <AlertTriangle size={12} />
                <span className="font-medium">Knowledge gaps:</span>
              </div>
              <div className="pl-4 mt-1">
                {trace.knowledge_gaps.map((gap, index) => (
                  <div key={`gap-${index}`} className="text-yellow-600">• {gap}</div>
                ))}
              </div>
            </div>
          )}

          {/* Self-Critique */}
          {trace.critique_score !== undefined && (
            <div className={`p-2 rounded ${trace.passed_critique ? 'bg-green-50' : 'bg-red-50'}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1">
                  {trace.passed_critique ? (
                    <CheckCircle size={12} className="text-green-600" />
                  ) : (
                    <AlertTriangle size={12} className="text-red-600" />
                  )}
                  <span className={`font-medium ${trace.passed_critique ? 'text-green-700' : 'text-red-700'}`}>
                    Self-Critique: {trace.passed_critique ? 'Passed' : 'Failed'}
                  </span>
                </div>
                <span className={`text-xs font-semibold ${getConfidenceColor(trace.critique_score / 100)}`}>
                  Score: {trace.critique_score}/100
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};