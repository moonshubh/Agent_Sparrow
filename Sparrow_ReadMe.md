# MB-Sparrow: A Multi-Agent AI System for Mailbird

**MB-Sparrow** is a production-grade, multi-agent AI system designed exclusively for Mailbird customer support. Its core mission is to transform the support experience through intelligent agent specialization, providing instant, accurate, and context-aware responses to user queries.

The system leverages a modern, full-stack architecture with a Python/FastAPI backend for agentic logic and a Next.js frontend for a seamless user experience.

## Core Architecture

The system is architected as a decoupled full-stack application. The user interacts with a web interface, which communicates with the backend via a FastAPI server. The server invokes a core LangGraph state machine, which routes the request to the appropriate specialized agent and streams back the response.

```mermaid
graph TD
    subgraph "Full System Architecture"
        subgraph "Frontend (Browser)"
            F[User] --> UI[Chat Interface];
        end
        subgraph "Backend (Server)"
            API[FastAPI Server]
            LG[LangGraph State Machine]
        end

        UI -- "HTTP Request/Stream" --> API;
        API -- "Invokes & Forwards" --> LG;
        
        subgraph "LangGraph Agents"
            direction LR
            Router{Query Router} --> PA[Primary Agent];
            Router --> LA[Log Analyst Agent];
            Router --> RA[Research Agent];
        end

        LG -- Contains --> Router;
        
        LG -- "Streams Response" --> API;
        API -- "Streams Response" --> UI;
    end
```

### Technology Stack
- **Backend**: FastAPI, LangGraph, Google Gemini 2.5, Supabase (PostgreSQL + pgvector), Redis, OpenTelemetry
- **Frontend**: Next.js 15, React, TypeScript, Tailwind CSS, shadcn/ui
- **Package Management**: `pip` & `requirements.txt` (Backend), `pnpm` (Frontend)

```mermaid
graph TD
    subgraph "Backend Architecture (LangGraph)"
        A[User Query] --> R{Query Router};
        R -- "route: primary_agent" --> PA[Primary Agent];
        R -- "route: log_analyst" --> LA[Log Analyst Agent];
        R -- "route: researcher" --> RA[Research Agent];
        PA --> O[Agent Output];
        LA --> O;
        RA --> O;
    end
```

This modular, agent-based architecture allows for clear separation of concerns and makes the system easily extensible.

## Frontend & UI Design

The frontend is a Next.js application styled with Tailwind CSS and shadcn/ui, featuring a design system aligned with Mailbird's branding.

-   **Unified Interface**: A single chat interface handles interactions with all agents.
-   **Markdown Support**: Responses from the Primary Support Agent are rendered as rich markdown.
-   **Custom Components**: Includes `LogAnalysisContainer` for structured data, `AgentAvatar` with Mailbird branding, and modern `MessageBubble` components.
-   **Branding**: Uses Mailbird blue (`#0095ff`) as the primary accent color throughout the interface.
-   **Accessibility**: Designed to be WCAG 2.1 AA compliant.

## Project Structure
```
MB-Sparrow-main/
├── app/                  # Backend FastAPI Application
│   ├── agents_v2/        # Core agent logic (router, primary, etc.)
│   ├── api/              # FastAPI endpoints
│   ├── core/             # Core configuration, security, settings
│   ├── db/               # Database interaction and embedding utils
│   └── tools/            # Agent tools
├── frontend/             # Frontend Next.js Application
│   ├── app/              # Next.js App Router (pages, layouts)
│   ├── components/       # Shared UI components
│   ├── lib/              # Utility functions, API types
│   ├── public/           # Static assets (images, etc.)
│   ├── package.json      # Frontend dependencies (managed by pnpm)
│   └── ...
├── tasks/               # Task definitions for task-master-ai
├── .env.example         # Example environment variables
├── main.py              # FastAPI entry point
├── requirements.txt     # Python dependencies
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- pnpm
- Supabase account (for database)
- Google Gemini API key
- Tavily API key (for web search)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-organization/mb-sparrow.git
   cd mb-sparrow
   ```

2. **Set up the backend**
   ```bash
   # Create and activate a virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Set up environment variables
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Set up the frontend**
   ```bash
   cd frontend
   pnpm install
   cp .env.example .env.local
   # Edit .env.local with your API URLs
   ```

### Running the Application

1. **Start the backend server** (from project root):
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

2. **Start the frontend development server** (from frontend/ directory):
   ```bash
   pnpm dev
   ```

3. **Access the application** at `http://localhost:3000`

## Development Workflow

This project uses a task-based development workflow managed by `task-master-ai`.

### Key Commands

- List all tasks: `task-master list`
- View next task: `task-master next`
- Mark task as done: `task-master set-status --id <task-id> --status done`
- Generate subtasks: `task-master expand --id <task-id>`

### Testing

Run the test suite with:
```bash
# Backend tests
pytest

# Frontend tests (from frontend/ directory)
pnpm test
```

## Configuration

### Environment Variables

#### Backend (`.env`)
```
# Required
GEMINI_API_KEY=your-gemini-api-key
DATABASE_URL=postgresql://user:password@host:port/dbname
TAVILY_API_KEY=your-tavily-api-key

# Optional
LOG_LEVEL=INFO
DEBUG=false
```

#### Frontend (`.env.local`)
```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
# Other frontend-specific variables
```

## Deployment

### Backend

Deploy the FastAPI application using a production ASGI server like Uvicorn with Gunicorn or deploy to a platform like Google Cloud Run, AWS ECS, or Heroku.

### Frontend

Build and export the Next.js application:
```bash
cd frontend
pnpm build
pnpm start  # For production
```

