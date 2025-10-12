/**
 * Advanced Agent Components
 * 
 * These components display the advanced reasoning and troubleshooting
 * capabilities of the Agent Sparrow primary agent.
 */

export { ReasoningTrace } from '../ReasoningTrace'
export { TroubleshootingWorkflow } from '../TroubleshootingWorkflow'

// Re-export types for convenience
export type { 
  ReasoningTraceProps,
  ReasoningStep,
  SolutionCandidate 
} from '../ReasoningTrace'

export type { 
  TroubleshootingWorkflowProps,
  DiagnosticStep,
  VerificationCheckpoint,
  TroubleshootingState 
} from '../TroubleshootingWorkflow'