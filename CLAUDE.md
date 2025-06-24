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

### 2. Agent Sparrow - Enhanced Primary Support Agent (`app/agents_v2/primary_agent/`)
- **Model**: `gemini-2.5-flash` - Advanced AI customer success expert
- **Reasoning**: Chain-of-thought processing with 6-phase reasoning pipeline
- **Intelligence**: Emotional intelligence with 8-state emotional analysis system
- **Problem Solving**: 5-step structured troubleshooting framework
- **Troubleshooting**: 7-phase structured workflows with progressive complexity (Level 1-5)
- **Session Management**: Complete troubleshooting session persistence and analytics
- **Escalation**: 5 intelligent escalation pathways with specialist routing
- **Tools**: Intelligent tool selection with reasoning transparency
- **Features**: Knowledge base search + web search with decision intelligence
- **UI**: Markdown rendering for formatted responses with headers, lists, code blocks

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

### 5. FeedMe - Customer Support Transcript Ingestion (`app/feedme/`)
- **Purpose**: Ingest customer support transcripts for reference knowledge
- **Processing**: Extract Q&A examples with AI-powered parsing and embedding
- **Integration**: Retrieval alongside knowledge base in Primary Agent responses
- **Features**: Upload management, processing status tracking, similarity search
- **Database**: PostgreSQL + pgvector for embedding-based retrieval
- **Config**: `FEEDME_ENABLED=true`, configurable thresholds and limits

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

### Recent Updates (2025-06-24)

#### Agent Sparrow v8.0 - Structured Troubleshooting Implementation
**Completed**: Comprehensive structured troubleshooting system with systematic diagnostic workflows

**Major Features:**
- **7-Phase Troubleshooting Workflow**: Initial Assessment → Basic Diagnostics → Intermediate Diagnostics → Advanced Diagnostics → Specialized Testing → Escalation Preparation → Resolution Verification
- **Progressive Complexity Handling**: 5-level difficulty scaling with customer adaptation (Level 1: Basic → Level 5: Specialist)
- **Diagnostic Step Sequencing**: Intelligent step progression with failure handling and alternative approaches
- **Verification Checkpoint System**: Automated validation with progress confirmation and quality assessment
- **Escalation Management**: 5 escalation pathways with intelligent criteria and specialist routing
- **Session State Management**: Complete session persistence with analytics and learning insights
- **Workflow Library**: 6 pre-built workflows for common problem categories with adaptive customization

**Technical Architecture:**
```python
# Structured troubleshooting integration with reasoning
troubleshooting_engine = TroubleshootingEngine(TroubleshootingConfig(
    enable_adaptive_workflows=True,
    enable_progressive_complexity=True,
    enable_verification_checkpoints=True,
    enable_automatic_escalation=True,
    integrate_with_reasoning_engine=True
))

# Workflow initiation based on reasoning analysis
troubleshooting_state = await troubleshooting_engine.initiate_troubleshooting(
    query_text=user_query,
    problem_category=reasoning_state.query_analysis.problem_category,
    customer_emotion=reasoning_state.query_analysis.emotional_state,
    reasoning_state=reasoning_state
)

# Adaptive workflow selection and session management
session = await troubleshooting_engine.start_troubleshooting_session(
    troubleshooting_state=troubleshooting_state,
    session_id=session_id
)
```

**Workflow Categories:**
- **Email Connectivity**: Basic (Level 2) and Advanced (Level 4) connectivity troubleshooting
- **Account Setup**: Guided setup with automatic and manual configuration paths
- **Sync Issues**: Email synchronization resolution with folder management
- **Performance Optimization**: System resource analysis and optimization
- **Feature Education**: Interactive learning with competency verification

**Files Created:**
- `app/agents_v2/primary_agent/troubleshooting/` - Complete structured troubleshooting framework
- `troubleshooting_engine.py` - Core orchestration engine with workflow management
- `diagnostic_sequencer.py` - Progressive step sequencing with complexity adaptation
- `verification_system.py` - Comprehensive checkpoint validation system
- `escalation_manager.py` - Intelligent escalation criteria and pathways
- `session_manager.py` - Session state management with analytics and persistence
- `workflow_library.py` - Pre-built workflows with progressive complexity handling
- `troubleshooting_schemas.py` - Complete data structures for troubleshooting state

**Files Enhanced:**
- `app/agents_v2/primary_agent/agent.py` - Integrated structured troubleshooting with reasoning framework

**Quality Assurance:**
- ✅ System Integration: Troubleshooting engine seamlessly integrated with reasoning framework
- ✅ Workflow Testing: 6 workflow categories tested with adaptive complexity scaling
- ✅ Session Management: Complete session lifecycle with analytics and persistence
- ✅ Progressive Complexity: 5-level difficulty adaptation with customer technical level matching
- ✅ Verification System: Automated checkpoint validation with quality assessment
- ✅ Escalation Pathways: 5 intelligent escalation routes with specialist requirements

**Previous Updates (2025-06-24)**

#### Agent Sparrow v7.0 - Advanced Reasoning Framework
**Completed**: Sophisticated AI reasoning system with emotional intelligence and structured problem-solving

**Major Features:**
- **6-Phase Reasoning Pipeline**: Query Analysis → Context Recognition → Solution Mapping → Tool Assessment → Response Strategy → Quality Assessment
- **Emotional Intelligence**: 8-state emotion detection (Frustrated, Confused, Anxious, Urgent, Professional, Satisfied, Neutral, Other) with pattern-based confidence scoring
- **5-Step Problem Solving**: Problem Definition → Information Gathering → Hypothesis Generation → Solution Implementation → Verification & Prevention
- **Intelligent Tool Decisions**: Sophisticated decision engine with reasoning transparency for optimal tool usage
- **Chain-of-Thought Processing**: Multi-step reasoning with evidence collection and alternative consideration
- **Quality Assessment**: Automated validation of reasoning clarity, solution completeness, and emotional appropriateness

**Technical Architecture:**
```python
# Core reasoning engine with comprehensive analysis
reasoning_engine = ReasoningEngine(ReasoningConfig(
    enable_chain_of_thought=True,
    enable_problem_solving_framework=True,
    enable_tool_intelligence=True,
    enable_quality_assessment=True,
    enable_reasoning_transparency=True
))

# 6-phase reasoning pipeline
reasoning_state = await reasoning_engine.reason_about_query(
    query=user_query,
    context={"messages": state.messages},
    session_id=getattr(state, 'session_id', 'default')
)

# Intelligent tool decision with reasoning
tool_decision = reasoning_state.tool_reasoning.decision_type
# Options: NO_TOOLS_NEEDED, INTERNAL_KB_ONLY, WEB_SEARCH_REQUIRED, 
#          BOTH_SOURCES_NEEDED, ESCALATION_REQUIRED
```

**Files Created:**
- `app/agents_v2/primary_agent/reasoning/` - Complete reasoning framework module
- `reasoning_engine.py` - Core 6-phase reasoning pipeline
- `tool_intelligence.py` - Sophisticated tool decision engine
- `problem_solver.py` - 5-step problem-solving framework
- `schemas.py` - Comprehensive data structures for reasoning state
- `prompts/agent_sparrow_prompts.py` - Advanced system prompts with emotional intelligence
- `prompts/emotion_templates.py` - 8-state emotional analysis system
- `prompts/response_formatter.py` - Response structure validation

**Files Enhanced:**
- `app/agents_v2/primary_agent/agent.py` - Integrated reasoning framework into agent workflow
- `app/agents_v2/primary_agent/prompts/__init__.py` - Modular prompt system

**Quality Assurance:**
- ✅ Syntax Validation: All Python modules pass compilation tests
- ✅ Integration Tests: Complete reasoning pipeline tested with real queries
- ✅ Emotional Intelligence: 8 emotional states with pattern-based detection
- ✅ Problem Categories: 7 problem types with specialized solution templates
- ✅ Tool Intelligence: 5 decision types with reasoning transparency
- ✅ Performance: Sub-second reasoning for typical customer queries

**Previous Updates (2025-06-23)**

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

## FeedMe Implementation

### FeedMe v1.0 - Customer Support Transcript Ingestion (Partial)
**Completed**: Core infrastructure for customer support transcript ingestion and processing

**Implementation Progress (2025-06-24):**

#### Phase 1: Core Infrastructure ✅ COMPLETED
**Environment Configuration:**
- Added 6 FeedMe-specific environment variables to `app/core/settings.py`
- Configurable file size limits, batch processing, similarity thresholds
- Feature flag support with `FEEDME_ENABLED` toggle

**Database Schema:**
- Created comprehensive database migration `002_create_feedme_tables.sql`
- `feedme_conversations` table: Full transcript storage with metadata and processing status
- `feedme_examples` table: Q&A examples with vector embeddings for similarity search
- Optimized indexes for both similarity search (ivfflat) and traditional queries
- Automated timestamp triggers and data integrity constraints

**Data Models:**
- Complete Pydantic schema system in `app/feedme/schemas.py`
- 20+ models covering conversations, examples, requests, responses, and analytics
- Comprehensive validation with enum types for status tracking
- Type-safe API contracts with full orm_mode support

**API Endpoints:**
- Full-featured FastAPI router in `app/api/v1/endpoints/feedme_endpoints.py`
- 12 endpoints covering upload, management, search, and analytics
- File upload support with size validation and encoding handling
- Pagination, filtering, and comprehensive error handling
- Processing status tracking and conversation management

**Key Features Implemented:**
```python
# Environment Configuration
FEEDME_ENABLED=true
FEEDME_MAX_FILE_SIZE_MB=10
FEEDME_MAX_EXAMPLES_PER_CONVERSATION=20
FEEDME_EMBEDDING_BATCH_SIZE=10
FEEDME_SIMILARITY_THRESHOLD=0.7
FEEDME_MAX_RETRIEVAL_RESULTS=3

# API Endpoints Available
POST /api/v1/feedme/conversations/upload     # Upload transcripts
GET  /api/v1/feedme/conversations            # List conversations  
GET  /api/v1/feedme/conversations/{id}       # Get conversation
PUT  /api/v1/feedme/conversations/{id}       # Update conversation
DELETE /api/v1/feedme/conversations/{id}     # Delete conversation
GET  /api/v1/feedme/conversations/{id}/examples # List examples
GET  /api/v1/feedme/conversations/{id}/status   # Processing status
POST /api/v1/feedme/search                  # Search examples
GET  /api/v1/feedme/analytics               # System analytics
POST /api/v1/feedme/conversations/{id}/reprocess # Reprocess transcript
```

**Database Tables:**
```sql
-- Conversations: Full transcript storage
feedme_conversations (
    id, title, original_filename, raw_transcript, parsed_content,
    metadata, uploaded_by, uploaded_at, processed_at, processing_status,
    error_message, total_examples, created_at, updated_at
)

-- Examples: Q&A pairs with embeddings
feedme_examples (
    id, conversation_id, question_text, answer_text, context_before, context_after,
    question_embedding, answer_embedding, combined_embedding, tags, issue_type,
    resolution_type, confidence_score, usefulness_score, is_active, 
    created_at, updated_at
)
```

**Files Created:**
- `app/feedme/__init__.py` - Module initialization with exports
- `app/feedme/schemas.py` - Comprehensive Pydantic models (400+ lines)
- `app/api/v1/endpoints/feedme_endpoints.py` - Full API router (600+ lines)
- `app/db/migrations/002_create_feedme_tables.sql` - Database schema

**Files Enhanced:**
- `app/core/settings.py` - Added 6 FeedMe configuration variables

#### Phase 2: Processing & Integration 🚧 IN PROGRESS
**Next Steps:**
- Celery task for transcript parsing and embedding generation
- Integration with `embedding_utils.py` for similarity search
- Primary Agent integration for FeedMe retrieval alongside KB search
- Frontend admin panel for transcript management

**Quality Assurance:**
- ✅ Database Schema: Comprehensive tables with proper indexes and constraints
- ✅ API Design: RESTful endpoints with full CRUD operations
- ✅ Data Validation: Type-safe Pydantic models with comprehensive validation
- ✅ Configuration: Environment-based settings with sensible defaults
- ✅ Error Handling: Comprehensive exception handling with user-friendly messages
- 🚧 Processing Pipeline: Celery integration pending
- 🚧 Search Integration: Embedding similarity search pending
- 🚧 Agent Integration: Primary Agent FeedMe retrieval pending

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

# FeedMe Configuration
FEEDME_ENABLED=true
FEEDME_MAX_FILE_SIZE_MB=10
FEEDME_MAX_EXAMPLES_PER_CONVERSATION=20
FEEDME_EMBEDDING_BATCH_SIZE=10
FEEDME_SIMILARITY_THRESHOLD=0.7
FEEDME_MAX_RETRIEVAL_RESULTS=3

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

**Last Updated**: 2025-06-24 | **Version**: 8.0 (Agent Sparrow Structured Troubleshooting Implementation)
**Next Review**: 2025-07-24
