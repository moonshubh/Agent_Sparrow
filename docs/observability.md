# Observability Guide

Last updated: 2026-02-12

All observability is consolidated within LangSmith — no Prometheus/Grafana/StatsD required.

## Table of Contents

1. [Setup & Configuration](#setup--configuration)
2. [What's Being Tracked](#whats-being-tracked)
3. [Using the LangSmith UI](#using-the-langsmith-ui)
4. [Common Monitoring Scenarios](#common-monitoring-scenarios)
5. [Alerting & Automation](#alerting--automation)
6. [Performance Analysis](#performance-analysis)
7. [Cost Optimization](#cost-optimization)
8. [Troubleshooting Playbooks](#troubleshooting-playbooks)

---

## Setup & Configuration

### Environment Variables

```bash
# Required for LangSmith tracing
LANGSMITH_API_KEY=your_api_key_here
LANGSMITH_PROJECT=agent-sparrow-production  # or staging/development
LANGSMITH_ENDPOINT=https://api.langsmith.com  # Optional, defaults to cloud

# Enable tracing in the application
LANGSMITH_TRACING_ENABLED=true
```

### Verification

Check that LangSmith is properly configured:

```python
# In app/core/tracing/__init__.py
# Logs: "LangSmith client initialized for project 'agent-sparrow-production'"
```

---

## What's Being Tracked

### 1. Model Routing & Fallbacks

**Location**: `app/agents/unified/model_router.py`

**Metadata Structure**:
```json
{
  "task_type": "coordinator",
  "selected_model": "gemini-2.5-flash",
  "fallback_occurred": true,
  "fallback_chain": ["gemini-2.5-pro", "gemini-2.5-flash"],
  "fallback_reason": "quota_exhausted",
  "models_attempted": 2,
  "final_model_health": {
    "available": true,
    "rpm_usage": "450/500",
    "rpd_usage": "8500/10000",
    "circuit_state": "closed"
  }
}
```

**Tags Added**:
- `model:gemini-2.5-flash`
- `coordinator_mode:heavy` or `coordinator_mode:light`
- `fallback:gemini-2.5-pro_to_gemini-2.5-flash`

### 2. Memory Operations

**Location**: `app/agents/unified/agent_sparrow.py`

**Scratchpad Location**: `state.scratchpad["_system"]["memory_stats"]`

**Tracked Metrics**:
```json
{
  "retrieval_attempted": true,
  "query_length": 156,
  "facts_retrieved": 5,
  "relevance_scores": [0.92, 0.87, 0.85, 0.81, 0.79],
  "retrieval_error": null,
  "write_attempted": true,
  "facts_extracted": 3,
  "facts_written": 3,
  "response_length": 512,
  "write_successful": true
}
```

### 3. Search Services

**Location**: `app/agents/unified/grounding.py`

**Gemini Grounding Metadata**:
```json
{
  "search_service": "gemini_grounding",
  "search_model": "gemini-2.5-flash",
  "results_count": 5,
  "max_results_requested": 5,
  "query_length": 42
}
```

**Fallback Search Metadata**:
```json
{
  "search_service": "fallback_chain",
  "fallback_reason": "quota_exceeded",
  "services_used": ["tavily", "firecrawl"],
  "tavily_success": true,
  "urls_found": 3,
  "firecrawl_attempts": 3,
  "firecrawl_successes": 2,
  "query_length": 42
}
```

### 4. AG-UI Stream Context

**Location**: `app/api/v1/endpoints/agui_endpoints.py`

**Enhanced Metadata**:
```json
{
  "session_id": "uuid-here",
  "trace_id": "trace-uuid",
  "agent_config": {
    "provider": "google",
    "model": "gemini-2.5-flash",
    "agent_type": "primary",
    "coordinator_mode": "light"
  },
  "feature_flags": {
    "memory_enabled": true,
    "grounding_enabled": true,
    "attachments_present": false,
    "attachments_count": 0,
    "force_websearch": false
  },
  "search_config": {
    "max_results": 10,
    "profile": "comprehensive"
  }
}
```

**Tags**:
- `agui-stream`
- `memory_enabled`
- `attachments:true` (when attachments present)
- `task_type:log_analysis` or `task_type:primary`

---

## Using the LangSmith UI

### Dashboard Views

1. **Project Overview**
   - Navigate to: Projects → agent-sparrow-production
   - View: Total runs, success rate, latency percentiles

2. **Run Analytics**
   - Automatic metrics: P50, P95, P99 latency
   - Token usage trends
   - Cost analysis (configure pricing in settings)

3. **Trace Explorer**
   - Detailed execution traces
   - Tool call results
   - Model routing decisions
   - Memory operations

### Filtering & Search

#### By Tags

```
# Find all runs using Pro model
tags contains "model:gemini-2.5-pro"

# Find memory-enabled sessions
tags contains "memory_enabled"

# Find runs with attachments
tags contains "attachments:true"

# Find specific agent types
tags contains "task_type:log_analysis"
```

#### By Metadata

```
# Find fallback events
metadata.fallback_occurred = true

# Find specific fallback reasons
metadata.fallback_reason = "quota_exhausted"

# Find high memory retrieval
metadata.facts_retrieved > 10

# Find specific search services
metadata.search_service = "tavily_fallback"
```

#### By Performance

```
# High latency runs
latency > 5000

# Failed runs
status = "error"

# High token usage
total_tokens > 10000

# Specific date ranges
start_time >= "2025-11-01" AND start_time < "2025-11-15"
```

---

## Common Monitoring Scenarios

### 1. Model Fallback Analysis

**Goal**: Understand why and how often fallbacks occur

**Query**:
```
metadata.fallback_occurred = true
```

**Analysis Steps**:
1. Group by `metadata.fallback_reason`
2. Check time patterns (peak hours?)
3. Correlate with `final_model_health.rpm_usage`
4. Review `fallback_chain` to understand progression

### 2. Memory Performance

**Goal**: Optimize memory retrieval and storage

**Filters**:
```
tags contains "memory_enabled"
```

**Metrics to Check**:
- Average `facts_retrieved`
- Distribution of `relevance_scores`
- `retrieval_error` frequency
- `write_successful` rate

### 3. Search Service Usage

**Goal**: Balance between Grounding, Tavily, and Firecrawl

**Queries**:
```
# Grounding usage
metadata.search_service = "gemini_grounding"

# Fallback usage
metadata.search_service = "fallback_chain"
```

**Analysis**:
- Compare `results_count` across services
- Check `firecrawl_successes` / `firecrawl_attempts` ratio
- Monitor `fallback_reason` distribution

### 4. Attachment Processing

**Goal**: Monitor log file and attachment handling

**Filter**:
```
tags contains "attachments:true"
```

**Check**:
- `attachments_count` distribution
- Correlation with `task_type:log_analysis`
- Impact on latency

---

## Alerting & Automation

### Setting Up LangSmith Alerts

1. **High Latency Alert**
   ```
   Rule: P95 latency > 10 seconds
   Action: Email/Slack notification
   ```

2. **Fallback Rate Alert**
   ```
   Rule: fallback_occurred rate > 30% in 1 hour
   Action: Investigate quota limits
   ```

3. **Memory Failure Alert**
   ```
   Rule: retrieval_error count > 5 in 10 minutes
   Action: Check memory service health
   ```

### Automated Reports

Create scheduled queries for:
- Daily fallback summary
- Weekly memory usage stats
- Monthly cost breakdown by model

---

## Performance Analysis

### Latency Breakdown

1. **Filter by percentile**:
   - P50: Expected performance
   - P95: Performance under load
   - P99: Worst-case scenarios

2. **Correlate with features**:
   ```
   # Memory impact
   Compare: memory_enabled vs not

   # Model impact
   Compare: coordinator_mode:heavy vs light

   # Attachment impact
   Compare: attachments:true vs false
   ```

### Token Usage Optimization

1. **High token consumers**:
   ```
   Sort by: total_tokens descending
   ```

2. **Optimization opportunities**:
   - Check `response_length` in memory stats
   - Review `query_length` patterns
   - Analyze tool call frequency

---

## Cost Optimization

### Model Usage Analysis

```python
# Pseudo-query for cost analysis
GROUP BY metadata.selected_model
AGGREGATE SUM(total_tokens) * model_price
```

### Recommendations

1. **Reduce Pro model usage**:
   - Check if `coordinator_mode:heavy` is necessary
   - Review fallback chains

2. **Optimize memory**:
   - Tune `memory_top_k` setting
   - Implement relevance threshold

3. **Search efficiency**:
   - Cache Grounding results
   - Reduce `max_results_requested`

---

## Troubleshooting Playbooks

### Playbook 1: High Fallback Rate

**Symptoms**: > 50% runs show `fallback_occurred: true`

**Investigation**:
1. Check `fallback_reason` distribution
2. Review `rpm_usage` and `rpd_usage` patterns
3. Look for time-based patterns
4. Check `circuit_state` values

**Solutions**:
- Increase rate limits if quota_exhausted
- Implement request queuing
- Add retry logic with backoff

### Playbook 2: Memory Retrieval Issues

**Symptoms**: `retrieval_error` or low `relevance_scores`

**Investigation**:
1. Check error messages in `retrieval_error`
2. Analyze `query_length` distribution
3. Review `facts_retrieved` counts
4. Check embedding service health

**Solutions**:
- Tune retrieval parameters
- Improve fact extraction logic
- Check Supabase connection

### Playbook 3: Search Service Failures

**Symptoms**: Low `firecrawl_successes` or missing results

**Investigation**:
1. Check `services_used` array
2. Review `tavily_success` rate
3. Analyze `urls_found` vs extracted
4. Check network/timeout issues

**Solutions**:
- Increase timeout settings
- Add retry logic
- Review rate limits for external services

### Playbook 4: Unexpected Latency Spikes

**Symptoms**: P95 latency > 2x normal

**Investigation**:
1. Check for correlation with:
   - `attachments_count`
   - `coordinator_mode:heavy`
   - `memory_enabled`
2. Review tool call patterns
3. Check external service latency

**Solutions**:
- Implement caching
- Optimize tool parallelization
- Add circuit breakers

---

## Best Practices

### 1. Tagging Strategy
- Always include model and agent_type tags
- Add feature flags as tags for easy filtering
- Use consistent tag naming conventions

### 2. Metadata Structure
- Keep metadata flat when possible for easier querying
- Include both counters and rates
- Add error messages for debugging

### 3. Regular Review
- Weekly: Check fallback rates and reasons
- Daily: Monitor latency percentiles
- Monthly: Analyze cost and token usage trends

### 4. Documentation
- Document any custom tags or metadata fields
- Keep this guide updated with new tracking
- Share common queries with the team

---

## Integration with Development Workflow

### Local Development
```bash
# Use development project
export LANGSMITH_PROJECT=agent-sparrow-dev

# Enable verbose tracing
export LANGSMITH_TRACING_ENABLED=true
export LANGCHAIN_VERBOSE=true
```

### Staging
```bash
# Use staging project
export LANGSMITH_PROJECT=agent-sparrow-staging

# Normal tracing
export LANGSMITH_TRACING_ENABLED=true
```

### Production
```bash
# Use production project
export LANGSMITH_PROJECT=agent-sparrow-production

# Selective tracing (if needed for performance)
export LANGSMITH_TRACING_ENABLED=true
export LANGSMITH_SAMPLE_RATE=0.1  # 10% sampling
```

---

## Appendix: Quick Reference

### Key Files
- `app/api/v1/endpoints/agui_endpoints.py` - Stream context
- `app/agents/unified/model_router.py` - Model fallbacks
- `app/agents/unified/agent_sparrow.py` - Memory stats
- `app/agents/unified/grounding.py` - Search tracking

### Environment Variables
- `LANGSMITH_API_KEY` - Required
- `LANGSMITH_PROJECT` - Project name
- `LANGSMITH_TRACING_ENABLED` - Enable/disable
- `LANGSMITH_ENDPOINT` - API endpoint

### Common Filters
- `tags contains "model:gemini-2.5-pro"`
- `metadata.fallback_occurred = true`
- `latency > 5000`
- `status = "error"`

### Support
- LangSmith Docs: https://docs.langsmith.com
- See also: [`docs/backend-architecture.md`](backend-architecture.md) for model routing and agent architecture
- See also: [`docs/RELIABILITY.md`](RELIABILITY.md) for retry and fallback patterns
