---
name: root-cause-tracing
description: Use when errors occur deep in execution and you need to trace back to find the original trigger. Systematically diagnoses error chains, distinguishes root cause from proximate cause, and integrates with log analysis tools.
---

# Root Cause Tracing Skill

## Overview

Systematic methodology for tracing errors back to their original source. Distinguishes between proximate causes (where the error manifests) and root causes (what actually triggered the failure). Complements Agent Sparrow's `log_diagnoser_tool`.

## When to Use

- Error occurs deep in execution stack
- Multiple errors cascade from single source
- Proximate cause is obvious but root cause unknown
- Need to prevent recurrence, not just fix symptom
- Complex systems with many interdependencies

## Core Concepts

### Root vs Proximate Cause

```
Proximate Cause: WHERE the error appears
   ↓
   Symptom → Symptom → Symptom
   ↑
Root Cause: WHAT actually triggered the failure
```

**Example**:
- Proximate: "Database connection timeout in API endpoint"
- Root: "Memory leak in connection pool causing exhaustion"

### Error Chain Anatomy

```
Root Cause (origin)
    ↓
Propagation (how it spreads)
    ↓
Amplification (how it worsens)
    ↓
Proximate Cause (where detected)
    ↓
User Impact (what they experience)
```

## Tracing Methodology

### Step 1: Document the Symptom

```markdown
## Error Report

**What was observed**:
[Exact error message/behavior]

**When it occurred**:
[Timestamp, frequency, pattern]

**Who/what reported it**:
[User, monitoring, logs]

**Impact scope**:
[Single user, all users, specific feature]

**Environment**:
[Production, staging, specific config]
```

### Step 2: Build the Timeline

```markdown
## Error Timeline

Work backwards from the error:

| Time | Event | Source |
|------|-------|--------|
| T+0 | Error observed | [where] |
| T-1 | [Previous event] | [source] |
| T-2 | [Earlier event] | [source] |
| ... | ... | ... |
| T-N | [Earliest related event] | [source] |

**Gap Analysis**:
- Missing logs between:
- Unclear transitions:
```

### Step 3: Trace the Chain

For each step in the error chain, ask:

```markdown
## Chain Analysis

### Error: [Description]
**Caused by**: [What triggered this?]
**Evidence**: [Log line, stack trace, metric]

### Error: [Previous in chain]
**Caused by**: [What triggered this?]
**Evidence**: [Log line, stack trace, metric]

[Continue until you reach something that should NOT have happened]

### ROOT CAUSE IDENTIFIED:
**What**:
**Why it happened**:
**Evidence**:
```

### Step 4: Validate Root Cause

```markdown
## Root Cause Validation

**Proposed Root Cause**: [Statement]

**Validation Questions**:

1. Does fixing this prevent the entire chain?
   [ ] Yes [ ] No [ ] Partially

2. Can you reproduce with this cause?
   [ ] Yes [ ] No [ ] Untested

3. Does timeline support this as origin?
   [ ] Yes [ ] No [ ] Unclear

4. Are there alternative explanations?
   [ ] None found
   [ ] Alternatives:

5. Why didn't existing safeguards catch it?
   [Explanation]

**Confidence Level**: [High/Medium/Low]
```

## Common Error Patterns

### Pattern: Cascade Failure

```
Resource Exhaustion → Connection Failure → Timeout → Retry Storm → Complete Outage
        ↑
    ROOT CAUSE: Memory leak / Config error / Traffic spike
```

**Tracing Tip**: Look for the first resource that hit limits.

### Pattern: Silent Corruption

```
Bad Data Written → Processing Continues → Aggregation Breaks → Report Fails
        ↑
    ROOT CAUSE: Validation bypass / Race condition / Encoding issue
```

**Tracing Tip**: Find when data was last known-good.

### Pattern: Dependency Failure

```
External Service Slow → Timeout → Retry → Queue Backlog → Memory Exhaustion
        ↑
    ROOT CAUSE: External dependency change / Network issue
```

**Tracing Tip**: Check external service health at error time.

### Pattern: Configuration Drift

```
Works in Dev → Fails in Prod → Different Error Each Time
        ↑
    ROOT CAUSE: Environment config mismatch / Missing secret / Version skew
```

**Tracing Tip**: Diff configurations across environments.

## Diagnostic Questions

### For Any Error

1. **What changed?** (deploy, config, traffic, dependency)
2. **When did it start?** (first occurrence, not first report)
3. **Who is affected?** (all users, subset, specific action)
4. **What's the blast radius?** (single component, system-wide)
5. **Has this happened before?** (check incident history)

### For Recurring Errors

1. **What's the pattern?** (time of day, traffic level, specific action)
2. **What's the workaround?** (does restart fix it? reprocessing?)
3. **What prevents detection?** (why don't we catch it earlier?)

## Log Analysis Integration

### Working with Agent Sparrow's Log Diagnoser

```markdown
## Combined Analysis Workflow

1. **Log Diagnoser Output**: [Summary from tool]

2. **Error Chain from Logs**:
   - Final error: [from logs]
   - Preceding errors: [from logs]
   - First anomaly: [from logs]

3. **Root Cause Hypothesis**:
   Based on log analysis, the root cause appears to be:
   [hypothesis]

4. **Additional Investigation Needed**:
   - [ ] Check [specific log/metric]
   - [ ] Verify [system state]
   - [ ] Test [hypothesis]
```

### Log Correlation Queries

```python
# Find related errors within time window
def find_error_chain(logs, error_time, window_minutes=5):
    """Extract all errors within window of main error."""
    start_time = error_time - timedelta(minutes=window_minutes)
    related = [
        log for log in logs
        if start_time <= log['timestamp'] <= error_time
        and log['level'] in ('ERROR', 'WARN', 'CRITICAL')
    ]
    return sorted(related, key=lambda x: x['timestamp'])

# Find first occurrence
def find_first_occurrence(logs, error_pattern):
    """Find earliest instance of error pattern."""
    matches = [
        log for log in logs
        if error_pattern in log['message']
    ]
    return min(matches, key=lambda x: x['timestamp']) if matches else None
```

## Quick Reference

| Symptom Type | Look For | Common Root Causes |
|--------------|----------|-------------------|
| Timeout | Resource metrics | Exhaustion, deadlock |
| Null/undefined | Data flow | Missing validation |
| Connection error | Network, deps | Config, firewall |
| Memory error | Allocation patterns | Leak, unbounded growth |
| Slow response | Timing metrics | N+1 queries, contention |

## Root Cause Report Template

```markdown
# Root Cause Analysis: [Incident Title]

**Date**: [Date]
**Severity**: [P1/P2/P3]
**Duration**: [Time to resolution]

## Summary

[One paragraph: what happened, root cause, resolution]

## Timeline

| Time | Event |
|------|-------|
| | |

## Root Cause

**What**: [Technical description]

**Why**: [How this state was reached]

**Evidence**: [Logs, metrics, traces]

## Contributing Factors

1. [Factor that made it worse/harder to detect]
2.

## Resolution

**Immediate fix**: [What stopped the bleeding]

**Permanent fix**: [What prevents recurrence]

## Action Items

| Action | Owner | Due |
|--------|-------|-----|
| | | |

## Lessons Learned

1.
2.
```

## Integration with Agent Sparrow

- **Log Diagnoser Enhancement**: Provides structured methodology for output
- **Escalation Support**: Systematic approach for complex issues
- **Incident Response**: Template for RCA documentation
- **Pattern Recognition**: Build library of known root causes

## Best Practices

1. **Resist first explanation** - First guess often wrong
2. **Follow the data** - Logs > intuition
3. **Question assumptions** - "It can't be X" often is X
4. **Time is information** - Exact timestamps matter
5. **Document as you go** - Memory fades, notes persist
