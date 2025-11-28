# Agent Sparrow Backend Architecture

## 1. Introduction (For Non-Technical Users)

**Agent Sparrow** is an intelligent AI platform designed to help users with complex tasks like research, log analysis, and document processing. Think of it as a super-powered assistant that doesn't just "chat" but can actually *do* things.

### What can it do?
*   **Chat & Reason**: It uses Google's **Gemini** models (the "brain") to understand your questions and provide smart answers.
*   **Read Documents (FeedMe)**: It can read PDFs, transcripts, and images. If a document is hard to read, it uses a special "FeedMe" system to extract text, and even asks for human approval if it's unsure.
*   **Analyze Logs**: It can look at technical log files to find errors and suggest fixes.
*   **Research**: It can browse the web to find the latest information.
*   **Remember**: It has a "Global Knowledge" system to remember facts and user preferences across conversations.

### How does it work?
Imagine a team of experts:
1.  **The Coordinator (Unified Agent)**: The main boss. It takes your request and decides who should handle it.
2.  **The Researcher**: A specialist that goes to the web to find answers.
3.  **The Analyst**: A specialist that reads technical logs.
4.  **The Librarian (Global Knowledge)**: Keeps track of important facts.

All these experts work together behind the scenes to give you a single, simple answer.

---

## 2. System Overview (For Developers)

Agent Sparrow is a **FastAPI**-based backend that powers the Agent Sparrow frontend. It utilizes **LangGraph** for orchestrating complex agent workflows and supports **multi-provider LLMs** (Google Gemini as the default and xAI Grok as an optional provider with reasoning mode).

### Key Technical Features
*   **Unified Agent Architecture**: A single entry point (`Unified Agent Sparrow`) that dynamically routes tasks to sub-agents (Research, Log Analysis) or tools.
*   **Multi-Provider LLMs**: Provider factory builds ChatGoogleGenerativeAI or ChatXAI (Grok 4.1) with reasoning-mode support; defaults remain Gemini.
*   **LangGraph Orchestration**: Uses a state-machine approach (Graph) to manage conversation flow, memory, and tool usage.
*   **DeepAgents Middleware**: A custom middleware stack for rate limiting, memory injection, and context management.
*   **FeedMe Ecosystem**: A comprehensive module for document ingestion, OCR (Optical Character Recognition), and "Intelligence" (summarization, sentiment analysis).
*   **Human-in-the-loop**: Built-in support for pausing execution to ask for human confirmation (e.g., for ambiguous text extraction).
*   **Real-time Streaming**: Uses Server-Sent Events (SSE) to stream answers token-by-token to the frontend.

### Tech Stack
*   **Framework**: Python 3.10+, FastAPI
*   **AI Models**: Google Gemini (2.5 Flash/Pro) and xAI Grok (4.1 Fast reasoning) via provider factory
*   **Database**: Supabase (PostgreSQL + pgvector)
*   **Async Tasks**: Celery + Redis
*   **Orchestration**: LangGraph v1
*   **Search**: Tavily, Firecrawl

---

## 3. Architecture Diagram

```mermaid
graph TB
    subgraph "Frontend Layer"
        NextJS[Next.js App]
        Copilot[Ag-UI Client]
    end

    subgraph "API Layer"
        FastAPI[FastAPI Server]
        StreamEP[Stream Endpoint<br/>/api/v1/copilot/stream]
        FeedMeEP[FeedMe API<br/>/api/v1/feedme/*]
        InterruptEP[Interrupt API<br/>/api/v1/v2/agent/*]
    end

    subgraph "Unified Agent Layer"
        Graph[LangGraph Orchestrator]
        Unified[Unified Agent Sparrow]
        
        subgraph "Sub-Agents"
            Researcher[Research Agent (Gemini default)]
            LogAnalyst[Log Diagnoser (Gemini default)]
        end
    end

    subgraph "FeedMe Ecosystem"
        Ingest[Ingestion Engine]
        Intel[Intelligence (Summaries)]
        Approval[Text Approval Workflow]
        OCR[Gemini Vision / OCR]
    end

    subgraph "Data & State"
        Supabase[(Supabase DB)]
        Redis[(Redis Cache)]
        GlobalKnow[Global Knowledge]
    end

    %% Connections
    NextJS --> Copilot
    Copilot --> StreamEP
    Copilot --> FeedMeEP
    
    StreamEP --> Graph
    Graph --> Unified
    Unified --> Researcher
    Unified --> LogAnalyst
    Unified --> ProviderFactory[(Provider Factory<br/>Gemini | Grok)]
    
    FeedMeEP --> Ingest
    FeedMeEP --> Intel
    FeedMeEP --> Approval
    
    Ingest --> OCR
    
    Unified --> GlobalKnow
    GlobalKnow --> Supabase
    
    Graph --> Redis
```

---

## 4. Directory Structure

The backend is organized into modular components within the `app/` directory:

```
app/
├── agents/                      # The "Brain" of the system
│   ├── unified/                 # The main Unified Agent logic
│   │   ├── agent_sparrow.py     # Main agent definition
│   │   ├── subagents.py         # Definitions for Research/Log agents
│   │   └── tools.py             # Tools (Search, FeedMe access)
│   ├── orchestration/           # LangGraph definitions
│   │   └── graph.py             # The state machine graph
│   └── streaming/               # SSE streaming logic
├── api/
│   └── v1/
│       └── endpoints/           # API Routes
│           ├── copilot_endpoints.py      # Main chat streaming
│           ├── feedme_intelligence.py    # AI analysis of docs
│           ├── text_approval_endpoints.py # Human approval workflow
│           └── agent_interrupt_endpoints.py # Human-in-the-loop controls
├── core/                        # Core settings, security, auth
├── db/                          # Database models and clients
├── feedme/                      # Document Processing Module
│   ├── ai_extraction_engine.py  # Gemini-powered extraction
│   ├── approval_workflow.py     # Human review logic
│   └── processors/              # PDF, Image processors
├── services/
│   └── global_knowledge/        # Long-term memory service
└── main.py                      # Application entry point
```

---

## 5. Core Components & Features

### A. Unified Agent (`app/agents/unified/`)
The core intelligence. Instead of having separate endpoints for different tasks, one "Unified Agent" handles everything.
*   **Model Routing**: Automatically picks the best model (e.g., `gemini-2.5-flash` for speed, `gemini-2.5-pro` for complex reasoning).
*   **Sub-Agents**: If you ask to "research X", it delegates to the **Research Subagent**. If you upload a log file, it uses the **Log Diagnoser**.

### B. FeedMe Ecosystem (`app/feedme/`)
A powerful engine for ingesting and understanding documents.
*   **Ingestion**: Upload PDFs, images, or transcripts.
*   **Intelligence**: Generates summaries, sentiment analysis, and "Smart Search" (semantic search) over your documents.
*   **Text Approval**: A workflow where low-confidence OCR scans are sent to a human queue for manual review/editing before being saved.

### C. Global Knowledge (`app/services/global_knowledge/`)
The system's long-term memory.
*   **Feedback**: Users can correct the agent.
*   **Persistence**: These corrections are saved to Supabase and recalled in future conversations to improve accuracy.

### D. Human-in-the-Loop (Interrupts)
The system can pause its work and ask the user for help.
*   **Endpoint**: `/api/v1/v2/agent/graph/run`
*   **Usage**: If the agent needs a decision (e.g., "Should I email this report?"), it halts and waits for a human "resume" command with a decision.

---

## 6. API Reference (Key Endpoints)

All API routes are prefixed with `/api/v1`.

| Feature | Endpoint | Description |
| :--- | :--- | :--- |
| **Chat** | `POST /copilot/stream` | Main streaming chat endpoint. Connects to LangGraph. |
| **FeedMe** | `POST /feedme/ingest` | Upload/Ingest a new document or transcript. |
| **Intelligence** | `POST /feedme/intelligence/summarize` | Generate an AI summary of a conversation. |
| **Approval** | `GET /feedme/approval/pending` | List documents waiting for human text approval. |
| **Approval** | `POST /feedme/approval/conversation/{id}/decide` | Approve, Reject, or Edit extracted text. |
| **Interrupts** | `POST /v2/agent/graph/run` | Resume a paused agent thread with a human decision. |
| **Logs** | `POST /agent/logs` | Analyze a raw log file (direct endpoint). |

---

## 7. Developer Guide

### Setting Up
1.  **Environment**: Create a `.env` file with your API keys (`GOOGLE_API_KEY`, `SUPABASE_URL`, etc.).
2.  **Dependencies**: Run `pip install -r requirements.txt`.
3.  **Database**: Ensure Supabase is running and migrations are applied.
4.  **Redis**: Required for Celery background tasks.

### Running the Server
```bash
# Start the API server
uvicorn app.main:app --reload --port 8000

# Start the FeedMe worker (for background processing)
celery -A app.feedme.celery_app worker --loglevel=info
```

### Adding a New Tool
1.  Define the tool function in `app/agents/unified/tools.py`.
2.  Register it in the `get_registered_tools()` function.
3.  The Unified Agent will automatically have access to it.

### Adding a New Endpoint
1.  Create a new file in `app/api/v1/endpoints/`.
2.  Define your `APIRouter`.
3.  Register the router in `app/main.py` using `app.include_router(...)`.

---

## 8. Deployment Notes
*   **Production**: Use `scripts/production-startup.sh` to launch with optimal settings.
*   **Observability**: The system integrates with **LangSmith** for tracing and debugging agent thought processes. Configure `LANGSMITH_API_KEY` to enable.
*   **Security**: API keys are encrypted at rest. Authentication is handled via Supabase JWTs.
