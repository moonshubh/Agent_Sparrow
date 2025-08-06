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