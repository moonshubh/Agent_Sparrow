# MB-Sparrow Backend Architecture Analysis for Rate Limiting

## Gemini Model Usage Points

Based on code analysis, here are all the locations where Gemini models are initialized and used:

### 1. Primary Agent (`app/agents_v2/primary_agent/agent.py`)
- **Model**: `gemini-2.5-flash`
- **Usage**: Customer support queries, main conversational agent
- **Rate Limit Risk**: MEDIUM (10 RPM / 250 RPD)
- **Initialization**: Line ~96
```python
model = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.environ.get("GEMINI_API_KEY"),
    safety_settings=safety_settings,
    convert_system_message_to_human=True
)
```

### 2. Enhanced Log Analysis Agent (`app/agents_v2/log_analysis_agent/enhanced_agent.py`)
- **Primary Model**: `gemini-2.5-pro`
- **Fallback Model**: `gemini-1.5-pro-latest`
- **Usage**: Complex log analysis and troubleshooting
- **Rate Limit Risk**: HIGH (5 RPM / 100 RPD for Pro model)
- **Initialization**: Lines ~54-64
```python
self.primary_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro",
    temperature=0.1,
    google_api_key=settings.gemini_api_key,
)
```

### 3. Router Agent (`app/agents_v2/router/router.py`)
- **Model**: `google/gemma-2b-it` (NOT Gemini - uses different provider)
- **Usage**: Query classification and routing
- **Rate Limit Risk**: NONE (Different provider)
- **Note**: This uses Gemma, not Gemini, so not subject to Gemini rate limits

### 4. Other Components Using Gemini Models
Based on grep results, these files also contain Gemini usage:

#### 4.1. Research Agent (`app/agents_v2/research_agent/research_agent.py`)
- **Model**: Likely Gemini (needs verification)
- **Usage**: Web research and synthesis

#### 4.2. Log Analysis Subcomponents
- `intelligent_analyzer.py`
- `advanced_solution_engine.py`
- `optimized_analyzer.py`
- `solution_engine.py`

#### 4.3. FeedMe Components
- `transcript_parser.py` - Uses Gemini for parsing transcripts

#### 4.4. Reflection Component
- `reflection/node.py` - Uses Gemini for reflection operations

## Critical Rate Limiting Points

### Priority 1: Core Agents (MUST implement)
1. **Primary Agent** - Main user interaction
2. **Enhanced Log Analysis Agent** - Most at risk due to Pro model limits

### Priority 2: Supporting Components (SHOULD implement)
3. **Research Agent** - Moderate usage
4. **FeedMe Transcript Parser** - Batch processing risk
5. **Reflection Component** - Lower priority

### Priority 3: Analysis Subcomponents (COULD implement)
6. **Log Analysis Subcomponents** - May be called by main agent

## Architecture Patterns

### Current Pattern
```
User Request → Router (Gemma) → [Primary Agent (Flash) | Log Agent (Pro)] → Response
```

### Required Rate Limiting Integration Points
1. **Agent Initialization** - Wrap model creation
2. **Agent Invocation** - Intercept before API calls
3. **Error Handling** - Graceful degradation on rate limits
4. **Monitoring** - Track usage across all agents

## Configuration Requirements

### Environment Variables Needed
```bash
# Rate Limiting Configuration
GEMINI_FLASH_RPM_LIMIT=8          # 80% of 10 RPM limit
GEMINI_FLASH_RPD_LIMIT=200        # 80% of 250 RPD limit
GEMINI_PRO_RPM_LIMIT=4            # 80% of 5 RPM limit  
GEMINI_PRO_RPD_LIMIT=80           # 80% of 100 RPD limit
RATE_LIMIT_REDIS_PREFIX=mb_sparrow_rl
RATE_LIMIT_CIRCUIT_BREAKER_ENABLED=true
```

### Redis Keys Structure
```
mb_sparrow_rl:flash:rpm:YYYY-MM-DD-HH-mm
mb_sparrow_rl:flash:rpd:YYYY-MM-DD
mb_sparrow_rl:pro:rpm:YYYY-MM-DD-HH-mm
mb_sparrow_rl:pro:rpd:YYYY-MM-DD
```

## Integration Strategy

### 1. Centralized Rate Limiter
Create a `GeminiRateLimiter` class that:
- Manages both Flash and Pro model limits
- Uses Redis for distributed tracking
- Implements circuit breaker pattern
- Provides async/await compatible interface

### 2. Agent Wrapper Pattern
Wrap existing model calls with rate limiting:
```python
@rate_limited(model="gemini-2.5-flash")
async def invoke_primary_agent(messages):
    # Existing logic
```

### 3. Graceful Degradation
- Queue requests when approaching limits
- Cache responses where possible
- Provide user-friendly error messages
- Implement exponential backoff

---
**Analysis Date**: 2025-07-01
**Files Analyzed**: 12 Python files containing Gemini usage
**Critical Components**: 2 (Primary Agent, Log Analysis Agent)