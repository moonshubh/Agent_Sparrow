export type TraceStepType = 'thought' | 'action' | 'result';

export interface TraceStepMetadata {
  [key: string]: any;
}

export interface TraceStep {
  id: string;
  timestamp: string;
  type: TraceStepType;
  content: string;
  metadata?: TraceStepMetadata;
}
