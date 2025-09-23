/**
 * Chat-related type definitions
 * Shared types for chat functionality across the frontend
 */

/**
 * Represents a chat message in the conversation
 */
export interface ChatMessage {
  /** Unique identifier for the message */
  id?: string;
  /** Role of the message sender */
  role: 'user' | 'assistant' | 'system';
  /** Content of the message */
  content: string;
  /** Optional agent type for assistant messages */
  agent_type?: 'primary' | 'log_analysis' | 'research' | 'router';
  /** Optional metadata including follow-up questions */
  metadata?: {
    follow_up_questions?: string[];
    [key: string]: any;
  };
  /** Timestamp of the message */
  timestamp?: string | Date;
}

/**
 * Agent session limits configuration
 */
export interface AgentSessionLimits {
  readonly primary: number;
  readonly log_analysis: number;
  readonly research: number;
  readonly router: number;
}

/**
 * Agent type keys
 */
export type AgentType = keyof AgentSessionLimits;

/**
 * Session limits by agent type
 */
export const AGENT_SESSION_LIMITS: AgentSessionLimits = {
  primary: 5,
  log_analysis: 3,
  research: 5,
  router: 10
} as const;

/**
 * Default fallback for session limits
 */
export const DEFAULT_SESSION_LIMIT = 5;

/**
 * Represents a chat session
 */
export interface ChatSession {
  id: string;
  title: string;
  agent_type: AgentType;
  is_active: boolean;
  message_count: number;
  created_at: string;
  updated_at: string;
  last_message_at?: string;
  metadata?: Record<string, any>;
}

/**
 * API request body for sending messages
 */
export interface SendMessageRequest {
  query: string;
  session_id?: string;
  messages?: ChatMessage[];
  agent_type?: AgentType;
}

/**
 * Confidence level union type
 */
export type ConfidenceLevel = 'HIGH' | 'MEDIUM' | 'LOW';

/**
 * Numeric confidence value between 0 and 1
 */
export type ConfidenceScore = number; // 0 to 1

/**
 * Reasoning phase types
 */
export type ReasoningPhase = 
  | 'QUERY_ANALYSIS'
  | 'CONTEXT_RECOGNITION'
  | 'SOLUTION_MAPPING'
  | 'TOOL_ASSESSMENT'
  | 'RESPONSE_STRATEGY'
  | 'QUALITY_ASSESSMENT';

/**
 * Complexity level types
 */
export type ComplexityLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'VERY_HIGH';

/**
 * Emotional state types
 */
export type EmotionalState = 
  | 'FRUSTRATED'
  | 'CONFUSED'
  | 'ANXIOUS'
  | 'URGENT'
  | 'PROFESSIONAL'
  | 'SATISFIED'
  | 'NEUTRAL'
  | 'OTHER';

/**
 * Problem category types
 */
export type ProblemCategory = 
  | 'EMAIL_CONNECTIVITY'
  | 'ACCOUNT_SETUP'
  | 'SYNC_ISSUES'
  | 'PERFORMANCE'
  | 'FEATURE_EDUCATION'
  | 'TECHNICAL_ERROR'
  | 'OTHER';

/**
 * Tool decision types
 */
export type ToolDecision = 
  | 'NO_TOOLS_NEEDED'
  | 'INTERNAL_KB_ONLY'
  | 'WEB_SEARCH_REQUIRED'
  | 'BOTH_SOURCES_NEEDED'
  | 'ESCALATION_REQUIRED';

/**
 * Individual thinking step in the reasoning process
 */
export interface ThinkingStep {
  /** The phase of reasoning */
  phase: ReasoningPhase;
  /** The thought or reasoning for this step */
  thought: string;
  /** Confidence score for this step (0 to 1) */
  confidence: ConfidenceScore;
}

/**
 * Complete thinking trace for message reasoning
 */
export interface ThinkingTrace {
  /** Overall confidence score (0 to 1) */
  confidence: ConfidenceScore;
  /** Sequential thinking steps */
  thinking_steps?: ThinkingStep[];
  /** Tool usage decision */
  tool_decision?: ToolDecision;
  /** Confidence level for tool decision */
  tool_confidence?: ConfidenceLevel;
  /** Identified knowledge gaps */
  knowledge_gaps?: string[];
  /** Detected emotional state */
  emotional_state?: EmotionalState;
  /** Categorized problem type */
  problem_category?: ProblemCategory;
  /** Complexity assessment */
  complexity?: ComplexityLevel;
  /** Self-critique score (0 to 1) */
  critique_score?: ConfidenceScore;
  /** Whether self-critique passed */
  passed_critique?: boolean;
}

/**
 * Source reference for citations
 */
export interface Source {
  id: string;
  title: string;
  url: string;
  snippet?: string;
  type: 'web' | 'knowledge_base' | 'documentation';
}

/**
 * Message metadata including thinking trace and follow-up questions
 */
export interface MessageMetadata {
  /** Confidence score for the response (0 to 1) */
  confidence?: ConfidenceScore;
  /** Source citations */
  sources?: Source[];
  /** Analysis results (for log analysis agent) */
  analysisResults?: any;
  /** Reason for routing to specific agent */
  routingReason?: string;
  /** Suggested follow-up questions */
  followUpQuestions?: string[];
  /** Number of follow-up questions that have been used */
  followUpQuestionsUsedCount?: number;
  /** Thinking trace for reasoning transparency */
  thinking_trace?: ThinkingTrace;
}