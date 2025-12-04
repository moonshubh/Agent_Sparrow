import { HttpAgent } from '@ag-ui/client';
import type { RunAgentInput, Message } from '@ag-ui/core';
import type { AttachmentInput } from './types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface AgentConfig {
  sessionId: string;
  traceId: string;
  provider?: string;
  model?: string;
  agentType?: string;
  useServerMemory?: boolean;
  attachments?: AttachmentInput[];
}

export function createSparrowAgent(config: AgentConfig) {
  const authToken = getAuthToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
  };

  // Only include Authorization header if token exists
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const agent = new HttpAgent({
    url: `${API_URL}/api/v1/agui/stream`,
    headers,
    threadId: config.sessionId,
  });

  // Set initial properties for agent.state
  agent.state = {
    session_id: config.sessionId,
    trace_id: config.traceId,
    provider: config.provider || 'google',
    model: config.model || 'gemini-2.5-flash',
    agent_type: config.agentType,
    use_server_memory: config.useServerMemory ?? true,
    attachments: config.attachments || [],
  };

  return agent;
}

// Helper to get auth token from localStorage or sessionStorage
function getAuthToken(): string {
  // Check localStorage first
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('authToken');
    if (token) return token;

    // Check session storage
    const sessionToken = sessionStorage.getItem('authToken');
    if (sessionToken) return sessionToken;
  }

  // Return empty string if no token found (anonymous access)
  return '';
}

// Export types for use in components
export type { Message, RunAgentInput } from '@ag-ui/core';