// /Users/shubhpatel/Downloads/MB-Sparrow-main/frontend/lib/api.ts

// --- Common Types ---
export interface ApiError {
  detail: string;
}

// --- Primary Support Agent (Chat Stream) ---
export interface PrimaryAgentChatRequestBody {
  message: string;
  model?: string;  // Optional model selection (e.g., 'google/gemini-2.5-flash', 'google/gemini-2.5-pro', 'moonshotai/kimi-k2')
  trace_id?: string;
}

export type PrimaryAgentStreamEventRole = "assistant" | "tool" | "error" | "system" | "user"; // Added system & user for completeness

export interface PrimaryAgentStreamEvent {
  role: PrimaryAgentStreamEventRole;
  content: string;
  trace_id?: string; // Optional: if we decide to send trace_id per event
}

// --- Research Agent --- 
export interface ChatMessage {
  id: string;
  type: "user" | "agent";
  content: string;
  timestamp: Date;
  agentType?: "general" | "log-analysis" | "research";
  feedback?: "positive" | "negative" | null;
}

export interface ResearchStep {
  type: string;
  description: string;
  status: "completed" | "in-progress";
}


// --- Log Analysis Agent (V2) ---

// Matches backend RawLogInput
export interface LogAnalysisRequestBody {
  content: string;
  trace_id?: string;
}

// Matches backend SystemMetadata
export interface SystemMetadata {
  mailbird_version: string;
  database_size_mb: string;
  account_count: string;
  folder_count: string;
  log_timeframe: string;
  analysis_timestamp: string;
}

// Matches backend IdentifiedIssue
export interface IdentifiedIssue {
  issue_id: string;
  signature: string;
  occurrences: number;
  severity: 'High' | 'Medium' | 'Low' | string; // Allow string for flexibility
  root_cause: string;
  user_impact: string;
  first_occurrence?: string | null;
  last_occurrence?: string | null;
}

// Matches backend ProposedSolution
export interface ProposedSolution {
  issue_id: string;
  solution_summary: string;
  solution_steps: string[];
  references: string[];
  success_probability: 'High' | 'Medium' | 'Low' | string;
}

// Matches backend SupplementalResearch
export interface SupplementalResearch {
  rationale: string;
  recommended_queries: string[];
}

// Matches backend StructuredLogAnalysisOutput
export interface LogAnalysisResponseBody {
  overall_summary: string;
  system_metadata: SystemMetadata;
  identified_issues: IdentifiedIssue[];
  proposed_solutions: ProposedSolution[];
  supplemental_research?: SupplementalResearch | null;
  trace_id?: string; // Keep trace_id for debugging
}

// --- Research Agent ---
export interface ResearchRequestBody {
  query: string;
  top_k?: number;
  trace_id?: string;
}

export interface ResearchItem {
  // Define the structure of a ResearchItem based on backend
  // Example:
  id: string;
  url: string;
  title: string;
  snippet?: string;
  source_name?: string; // e.g., "Web Search", "Internal KB"
  score?: number; // Relevance score
}

export interface ResearchResponseBody {
  results: ResearchItem[];
  trace_id?: string;
}

// --- General API Function Types (Optional, for SWR or react-query hooks) ---

// Example for a generic POST request function
// export type PostRequestFunction<TBody, TResponse> = (
//   url: string,
//   body: TBody,
//   token?: string // If auth is needed later
// ) => Promise<TResponse>;

// Example for a streaming request
// export type StreamRequestFunction<TBody, TEvent> = (
//   url: string,
//   body: TBody,
//   onMessage: (event: TEvent) => void,
//   onError?: (error: ApiError | Error) => void,
//   onClose?: () => void,
//   token?: string
// ) => Promise<void>; // Or a controller to abort the stream
