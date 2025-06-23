# CLAUDE.md - MB-Sparrow Agent System

## Project Context & Mission

MB-Sparrow is a production-grade, multi-agent AI system built exclusively for Mailbird customer support. Core mission: Transform customer support through intelligent agent specialization with instant, accurate responses.

### Architecture Flow
```
User Query → Unified Interface → Router → [Primary | Log Analyst | Research] → Response
```

### Technology Stack
**Backend**: FastAPI + LangGraph + Gemini 2.5 + Supabase/pgvector + Redis + OpenTelemetry
**Frontend**: Next.js 15 + shadcn/ui + Tailwind CSS + TypeScript + Mailbird blue branding

## Agent Specifications

### 1. Query Router (`app/agents_v2/router/`)
- **Model**: `google/gemma-2b-it` - Fast query classification
- **Function**: Route queries to appropriate agent (confidence threshold: 0.6)
- **Fallback**: Primary agent on low confidence/errors

### 2. Primary Support Agent (`app/agents_v2/primary_agent/`)
- **Model**: `gemini-2.5-flash` - General Mailbird support
- **Features**: Knowledge base search (0.75 threshold) + web search fallback
- **UI**: Markdown rendering for formatted responses with headers, lists, code blocks
- **Tools**: `mailbird_kb_search`, `tavily_web_search`

### 3. Enhanced Log Analysis Agent (`app/agents_v2/log_analysis_agent/`)
- **Model**: `gemini-2.5-pro` - Comprehensive log analysis
- **Capabilities**: System profiling, issue detection, solution generation, executive summaries
- **Analysis**: 7 issue categories with severity classification and confidence scoring
- **Output**: Structured log analysis container with markdown executive summaries
- **Config**: `USE_ENHANCED_LOG_ANALYSIS=true`, `ENHANCED_LOG_MODEL=gemini-2.5-pro`

### 4. Research Agent (`app/agents_v2/research_agent/`)
- **Model**: `gemini-2.5-flash/pro` - Multi-step web research
- **Features**: 3-stage pipeline (Search → Scrape → Synthesize) with citations
- **Caching**: Redis 24-hour TTL with rate limiting

## UI Components & Design System

### Core Components
- **UnifiedChatInterface**: Main conversational interface with welcome → chat state transitions  
- **MessageBubble**: Modern chat bubbles with Mailbird blue branding and markdown support
- **AgentAvatar**: Standardized avatar with Agent Sparrow logo and blue accent ring
- **MarkdownMessage**: Primary support responses with rich formatting (headers, lists, code)
- **LogAnalysisContainer**: Structured display for system health, issues, and solutions
- **InputSystem**: Search-style input with file upload and drag-and-drop

### Design System
- **Colors**: Mailbird blue (#0095ff light, #38b6ff dark) as accent throughout
- **Typography**: Inter font with improved prose styling and contrast ratios
- **Avatars**: Agent Sparrow logo with blue accent rings for all agent messages
- **Bubbles**: User bubbles with blue accent background, agent bubbles with neutral styling
- **Accessibility**: WCAG 2.1 AA compliant with proper focus indicators and semantic HTML

### Recent Updates (2025-06-23)

#### Chat Polish v6.1
**Completed**: Comprehensive UI refinement with Mailbird brand integration

**Key Improvements:**
- **Mailbird Blue Integration**: Consistent #0095ff accent color across all components
- **Enhanced Message Bubbles**: User bubbles with blue accent, improved contrast for light theme
- **Agent Avatar System**: Standardized AgentAvatar component with logo and blue ring
- **Markdown Rendering**: Primary support responses now render formatted markdown (headers, lists, code)
- **Assistant Label Removal**: Clean agent responses without green "Assistant" ribbons
- **Improved User Experience**: Better contrast ratios and professional appearance

**Technical Implementation:**
```typescript
// AgentAvatar component with Mailbird branding
<Avatar className="ring-1 ring-accent/30 bg-accent/10">
  <AvatarImage src="/agent-sparrow.png" alt="Agent Sparrow" />
  <AvatarFallback className="bg-accent/10 text-accent">AS</AvatarFallback>
</Avatar>

// User bubble with Mailbird blue styling  
className="bg-accent/10 border-accent/30 text-foreground"

// Markdown rendering for primary support
{agentType === 'primary' && !isUser ? (
  <MarkdownMessage content={content} />
) : (
  <div className="text-sm leading-relaxed">{content}</div>
)}
```

**Files Modified:**
- `components/ui/AgentAvatar.tsx` - New standardized avatar component
- `components/markdown/MarkdownMessage.tsx` - Rich markdown rendering for primary support
- `components/chat/MessageBubble.tsx` - Updated styling, avatar integration, assistant label removal
- `app/globals.css` - Mailbird blue accent colors (already configured)
- `public/` - Removed unused placeholder files

**Quality Assurance:**
- ✅ Build Success: TypeScript compilation with zero errors
- ✅ Test Coverage: 32 tests passing across 5 test files  
- ✅ Accessibility: WCAG 2.1 AA compliance maintained
- ✅ Brand Consistency: Mailbird blue accent throughout interface

## Development Guidelines

### Code Standards
- **TypeScript**: Strict mode with comprehensive type safety
- **React**: Functional components with hooks, proper prop typing  
- **Styling**: Tailwind utility classes with custom CSS variables
- **Testing**: Vitest with React Testing Library, >80% coverage
- **Accessibility**: WCAG 2.1 AA compliance for all components

### Key Patterns
- **Agent Routing**: Backend handles all routing decisions transparently
- **Markdown Support**: ReactMarkdown with remarkGfm for rich text formatting
- **Avatar System**: Consistent AgentAvatar usage for all agent representations
- **Color System**: CSS custom properties for theme-aware Mailbird blue branding
- **State Management**: React hooks with custom API integration patterns

## Configuration

### Environment Variables
```bash
# Agent Configuration
ROUTER_CONF_THRESHOLD=0.6
USE_ENHANCED_LOG_ANALYSIS=true  
ENHANCED_LOG_MODEL=gemini-2.5-pro

# Performance Settings
OPTIMIZATION_THRESHOLD_LINES=500
USE_OPTIMIZED_ANALYSIS=true
```

### Development Commands
```bash
# Frontend Development
npm run dev          # Start development server
npm run build        # Production build
npm test            # Run test suite
npm test -- -u      # Update snapshots

# Quality Assurance  
npm run lint        # ESLint validation
npm run typecheck   # TypeScript validation
```

## Success Metrics
- **System Availability**: >99.9% uptime
- **Response Latency**: <2s for 95% of queries  
- **User Satisfaction**: >4.5/5 average rating
- **Resolution Rate**: >90% queries resolved without escalation

---

**Last Updated**: 2025-06-23 | **Version**: 6.1 (Chat Polish with Mailbird Branding)
**Next Review**: 2025-07-23
