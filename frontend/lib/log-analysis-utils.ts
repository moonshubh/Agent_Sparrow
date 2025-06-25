/**
 * Utility functions for log analysis components
 */

import { type VariantProps } from "class-variance-authority"
import { badgeVariants } from "@/components/ui/badge"

export type SeverityLevel = "Critical" | "High" | "Medium" | "Low" | "critical" | "high" | "medium" | "low"
export type HealthStatus = "Healthy" | "Degraded" | "Critical" | "healthy" | "degraded" | "critical"

/**
 * Maps severity levels to badge variants with semantic colors
 */
export const severityVariant = (severity: string): VariantProps<typeof badgeVariants>["variant"] => {
  const normalizedSeverity = severity?.toLowerCase()
  
  const mapping = {
    'critical': 'destructive',
    'high': 'outline', 
    'medium': 'secondary',
    'low': 'secondary'
  } as const
  
  return mapping[normalizedSeverity as keyof typeof mapping] ?? 'secondary'
}

/**
 * Gets Tailwind classes for severity-based styling with improved WCAG AA compliance
 */
export const severityClasses = (severity: string) => {
  const normalizedSeverity = severity?.toLowerCase()
  
  switch (normalizedSeverity) {
    case "critical":
      return {
        bg: "bg-red-600/10 dark:bg-red-600/10",
        border: "border-red-500/20 dark:border-red-500/40",
        text: "text-red-600 dark:text-red-400",
        icon: "text-red-600 dark:text-red-400"
      }
    case "high":
      return {
        bg: "bg-orange-500/5 dark:bg-orange-500/10", 
        border: "border-orange-500/20 dark:border-orange-500/40",
        text: "text-orange-600 dark:text-orange-400",
        icon: "text-orange-600 dark:text-orange-400"
      }
    case "medium":
      return {
        bg: "bg-amber-400/10 dark:bg-amber-400/10",
        border: "border-amber-500/20 dark:border-amber-400/40", 
        text: "text-amber-600 dark:text-amber-300",
        icon: "text-amber-600 dark:text-amber-300"
      }
    case "low":
      return {
        bg: "bg-muted dark:bg-neutral-800/60 backdrop-blur",
        border: "border-border",
        text: "text-foreground",
        icon: "text-muted-foreground"
      }
    default:
      return {
        bg: "bg-muted dark:bg-neutral-800/60 backdrop-blur",
        border: "border-border",
        text: "text-foreground", 
        icon: "text-muted-foreground"
      }
  }
}

/**
 * Gets health status styling with improved contrast
 */
export const healthStatusClasses = (status: string) => {
  const normalizedStatus = status?.toLowerCase()
  
  switch (normalizedStatus) {
    case "critical":
      return {
        bg: "bg-red-600/10 dark:bg-red-600/10",
        text: "text-red-600 dark:text-red-400",
        icon: "text-red-600 dark:text-red-400"
      }
    case "degraded":
      return {
        bg: "bg-amber-400/10 dark:bg-amber-400/10",
        text: "text-amber-600 dark:text-amber-300", 
        icon: "text-amber-600 dark:text-amber-300"
      }
    case "healthy":
      return {
        bg: "bg-green-600/10 dark:bg-green-500/10",
        text: "text-green-700 dark:text-green-400",
        icon: "text-green-700 dark:text-green-400"
      }
    default:
      return {
        bg: "bg-muted dark:bg-neutral-800/60 backdrop-blur",
        text: "text-muted-foreground",
        icon: "text-muted-foreground"
      }
  }
}

/**
 * Formats success probability for display
 */
export const formatSuccessProbability = (probability: string | number): string => {
  if (typeof probability === "number") {
    return `${Math.round(probability * 100)}%`
  }
  
  if (typeof probability === "string") {
    const normalized = probability.toLowerCase()
    switch (normalized) {
      case "high":
        return "90%+"
      case "medium": 
        return "60-90%"
      case "low":
        return "<60%"
      default:
        return probability
    }
  }
  
  return "Unknown"
}

/**
 * Formats time estimates consistently
 */
export const formatTimeEstimate = (timeStr: string | number): string => {
  if (typeof timeStr === "number") {
    return `${timeStr} min`
  }
  
  if (typeof timeStr === "string") {
    // Handle various formats like "15-30 minutes", "Day 1", "1 hour", etc.
    return timeStr.replace(/minutes?/gi, "min").replace(/hours?/gi, "hr")
  }
  
  return "Unknown"
}

/**
 * Type definitions for log analysis data structures
 */
export interface SystemStats {
  health_status?: string
  mailbird_version?: string
  account_count?: number
  folder_count?: number
  database_size_mb?: number
}

// Enhanced Issue Definition with Backend v3.0 Alignment
export interface LogIssue {
  id?: string
  issue_id?: string
  severity: SeverityLevel
  category: string
  title?: string
  description?: string
  impact?: string
  root_cause?: string
  frequency_pattern?: string
  affected_accounts?: string[]
  occurrences?: number
  user_impact?: string
  // Enhanced backend fields
  signature?: string
  first_occurrence?: string
  last_occurrence?: string
  error_type?: string
  stack_trace?: string
  correlation_id?: string
  business_impact?: string
  technical_details?: Record<string, any>
  remediation_status?: 'pending' | 'in_progress' | 'resolved' | 'ignored'
  priority_score?: number
  related_issues?: string[]
}

export interface LogSolution {
  id?: string
  solution_id?: string
  title?: string
  summary?: string
  solution_summary?: string
  details?: string
  description?: string
  priority: SeverityLevel
  estimated_time?: string
  estimated_time_minutes?: number
  estimated_total_time_minutes?: number
  eta_min?: number
  success_probability?: string | number
  success_prob?: string | number
  implementation_steps?: Array<{
    step_number: number
    action?: string
    description?: string
    details?: Record<string, any>
    specific_settings?: Record<string, any>
    expected_outcome?: string
  }>
  steps?: Array<string | {
    step_number: number
    action?: string
    description?: string
    details?: Record<string, any>
    specific_settings?: Record<string, any>
    expected_outcome?: string
  }>
  expected_outcome?: string
  affected_accounts?: string[]
  implementation_timeline?: string
}

// Enhanced Backend Schema Types (v3.0) - Complete Backend Alignment

export interface DetailedSystemMetadata {
  mailbird_version: string
  database_size_mb: number
  account_count: number
  folder_count: number
  memory_usage_mb?: number
  startup_time_ms?: number
  email_providers: string[]
  sync_status?: string
  os_version?: string
  system_architecture?: string
  log_timeframe: string
  analysis_timestamp: string
  total_entries_parsed: number
  error_rate_percentage: number
  log_level_distribution: Record<string, number>
  // Additional backend fields for complete alignment
  cpu_usage_percentage?: number
  disk_usage_gb?: number
  network_latency_ms?: number
  last_sync_timestamp?: string
  active_connections?: number
  failed_operations_count?: number
  system_uptime_hours?: number
}

export interface EnvironmentalContext {
  os_version: string
  platform: string
  antivirus_software: string[]
  firewall_status: string
  network_type: string
  proxy_configured: boolean
  system_locale: string
  timezone: string
}

export interface CorrelationAnalysis {
  temporal_correlations: Array<Record<string, any>>
  account_correlations: Array<Record<string, any>>
  issue_type_correlations: Array<Record<string, any>>
  correlation_matrix: Record<string, any>
  analysis_summary: Record<string, any>
}

export interface DependencyAnalysis {
  graph_summary: Record<string, any>
  root_causes: string[]
  primary_symptoms: string[]
  cyclical_dependencies: string[][]
  centrality_measures: Record<string, any>
  issue_relationships: Array<Record<string, any>>
}

export interface PredictiveInsight {
  issue_type: string
  probability: number
  timeframe: string
  early_indicators: string[]
  preventive_actions: string[]
  confidence_score: number
}

export interface MLPatternDiscovery {
  patterns_discovered: Array<Record<string, any>>
  pattern_confidence: Record<string, number>
  clustering_summary: Record<string, any>
  recommendations: string[]
}

export interface AnalysisMetrics {
  analysis_duration_seconds: number
  parser_version: string
  llm_model_used: string
  web_search_performed: boolean
  confidence_threshold_met: boolean
  completeness_score?: number
}

export interface ValidationSummary {
  is_valid: boolean
  issues_found: string[]
  warnings: string[]
  suggestions: string[]
  preprocessing_applied: boolean
  detected_language: string
  detected_platform: string
}

export interface EnhancedSolutionStep {
  step_number: number
  description: string
  expected_outcome: string
  troubleshooting_note?: string
  estimated_time_minutes?: number
  risk_level?: string
  platform_specific?: string
  automated_script?: string
  validation_command?: string
  rollback_procedure?: string
}

export interface EnhancedSolution extends LogSolution {
  issue_id?: string  // Add missing issue_id property
  solution_steps: EnhancedSolutionStep[]
  platform_compatibility: string[]
  automated_tests: Array<Record<string, any>>
  remediation_script?: string
  rollback_script?: string
  success_criteria: string[]
  requires_restart: boolean
  data_backup_required: boolean
}

// Comprehensive Enhanced Analysis Response - Full Backend v3.0 Schema
export interface EnhancedLogAnalysisData {
  // Executive Summary
  overall_summary: string
  health_status: string
  priority_concerns: string[]
  
  // Detailed System Information
  system_metadata: DetailedSystemMetadata
  environmental_context: EnvironmentalContext
  
  // Issue Analysis
  identified_issues: LogIssue[]
  issue_summary_by_severity: Record<string, number>
  
  // Enhanced Analysis (v3.0)
  correlation_analysis: CorrelationAnalysis
  dependency_analysis: DependencyAnalysis
  predictive_insights: PredictiveInsight[]
  ml_pattern_discovery: MLPatternDiscovery
  
  // Solution Guidance
  proposed_solutions: EnhancedSolution[]
  
  // Research Recommendations
  supplemental_research?: {
    rationale: string
    recommended_queries: string[]
    research_priority: string
    expected_information: string
    alternative_resources?: string[]
  }
  
  // Analysis Metadata
  analysis_metrics: AnalysisMetrics
  validation_summary: ValidationSummary
  
  // Recommendations
  immediate_actions: string[]
  preventive_measures: string[]
  monitoring_recommendations: string[]
  automated_remediation_available: boolean
  
  // Additional Backend v3.0 Fields
  system_profile?: SystemProfile
  account_analysis?: AccountAnalysis[]
  temporal_analysis?: TemporalAnalysis
  security_assessment?: SecurityAssessment
  performance_insights?: PerformanceInsights
  automation_recommendations?: AutomationRecommendation[]
  
// Trace ID
  trace_id?: string
}

// Additional v3.0 Backend Interface Definitions
export interface SystemProfile {
  profile_id: string
  system_type: string
  performance_category: string
  resource_utilization: Record<string, number>
  stability_metrics: Record<string, number>
  optimization_opportunities: string[]
}

export interface AccountAnalysis {
  account: string
  email_provider: string
  status: string
  total_issues: number
  primary_issues: Array<[string, number]>
  sync_performance: Record<string, any>
  connection_stability: Record<string, any>
  error_patterns: string[]
  recommendations: string[]
}

export interface TemporalAnalysis {
  time_range: string
  peak_activity_periods: string[]
  issue_frequency_patterns: Record<string, number>
  performance_trends: Record<string, number>
  seasonal_patterns: Record<string, any>
}

export interface SecurityAssessment {
  security_score: number
  vulnerabilities_found: string[]
  security_recommendations: string[]
  compliance_status: Record<string, string>
  encryption_status: Record<string, boolean>
  access_control_issues: string[]
}

export interface PerformanceInsights {
  overall_score: number
  bottlenecks_identified: string[]
  optimization_recommendations: string[]
  resource_usage_analysis: Record<string, number>
  latency_analysis: Record<string, number>
  throughput_metrics: Record<string, number>
}

export interface AutomationRecommendation {
  automation_id: string
  title: string
  description: string
  automation_type: string
  complexity_level: string
  estimated_setup_time: number
  potential_benefits: string[]
  requirements: string[]
  automation_script?: string
}

// Legacy compatibility type (for backwards compatibility)
export interface LogAnalysisData {
  system_metadata?: SystemStats
  system_stats?: SystemStats
  identified_issues?: LogIssue[]
  detailed_issues?: LogIssue[]
  proposed_solutions?: LogSolution[]
  priority_solutions?: LogSolution[]
  executive_summary?: string
  executive_summary_md?: string
  overall_summary?: string  // Backend field name for executive summary
  immediate_actions?: string[]
  health_status?: string
  priority_concerns?: string[]
}