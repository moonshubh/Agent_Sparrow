# Agent Sparrow Frontend Architecture

> **Last updated**: 2026-02-12
>
> Canonical frontend architecture overview. Covers platform choices, directory strategy, and AG-UI protocol integration.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Directory Structure](#2-directory-structure)
3. [AG-UI Protocol Integration](#3-ag-ui-protocol-integration)
4. [Frontend Reference (Features, State, Services, Routing, Patterns)](frontend-reference.md)

---

## 1. Overview

Agent Sparrow's frontend is a **Next.js 16** App Router application built with **React 19** and **TypeScript 5.9** in strict mode. It provides a real-time multi-agent chat interface, a document ingestion system (FeedMe), and a 3D knowledge graph visualization (Memory UI).

### Core Technology Stack

| Category | Technology | Version |
|----------|-----------|---------|
| Framework | Next.js (App Router, Turbopack default) | ^16.1.6 |
| UI Library | React | 19.2.4 |
| Language | TypeScript (strict mode) | ^5.9.3 |
| Styling | Tailwind CSS | 3.4.17 |
| Component Library | shadcn/ui (Radix UI primitives) | Latest |
| State Management | Zustand | ^5.0.11 |
| Server State | TanStack React Query | 5.90.20 |
| 3D Visualization | react-three-fiber + drei + Three.js | ^9.5.0 / ^10.7.7 / ^0.182.0 |
| Rich Text | TipTap | 3.19.0 |
| Form Handling | React Hook Form + Zod | ^7.71.1 / ^4.3.6 |
| Animation | Framer Motion | ^12.31.0 |
| Markdown | react-markdown + remark/rehype plugins | 10.1.0 |
| Charts | Recharts | 3.7.0 |
| Streaming | Native SSE via AG-UI protocol | Custom |
| Auth | Supabase Auth (@supabase/ssr) | ^0.8.0 |
| Testing | Vitest + Testing Library | ^4.0.18 |
| Package Manager | pnpm | 10.12.1 |
| Node.js | >= 20.9.0 | Required |

### Architecture Pattern

The application follows a **feature-based modular architecture** where each domain (chat, feedme, memory, auth, settings, zendesk) is self-contained under `src/features/`. Cross-cutting concerns live in `src/shared/` and `src/services/`. Streaming communication with the backend uses a custom AG-UI protocol implementation over SSE -- there is no CopilotKit dependency.

---

## 2. Directory Structure

```
frontend/
├── middleware.ts                    # Auth guard, route protection, settings redirect
├── next.config.js                   # Rewrites, security headers, katex alias
├── src/
│   ├── app/                         # Next.js App Router pages and layouts
│   │   ├── layout.tsx               # Root layout (ThemeProvider, AuthProvider, QueryProvider)
│   │   ├── page.tsx                 # Root redirect -> /chat
│   │   ├── globals.css              # Global CSS
│   │   ├── chat/
│   │   │   └── page.tsx             # Chat page (dynamically imports LibreChatClient)
│   │   ├── feedme/
│   │   │   ├── page.tsx             # FeedMe hub page (Dock navigation, dialogs)
│   │   │   └── conversation/[id]/
│   │   │       └── page.tsx         # Individual FeedMe conversation view
│   │   ├── memory/
│   │   │   └── page.tsx             # Memory UI (dynamically imports MemoryClient)
│   │   ├── login/
│   │   │   └── page.tsx             # OAuth login (Google)
│   │   └── auth/
│   │       └── callback/
│   │           └── page.tsx         # Supabase OAuth callback handler
│   │
│   ├── features/                    # Domain-specific feature modules
│   │   ├── auth/                    # Auth components (GoogleLoginForm, ProtectedRoute, UserMenu)
│   │   ├── librechat/               # Chat UI (LibreChatClient, AgentContext, MessageItem, ThinkingPanel)
│   │   ├── feedme/                  # FeedMe (Dock, dialogs, UnifiedTextCanvas, stats)
│   │   ├── memory/                  # Memory UI (3D graph, table, TipTap editor, hooks)
│   │   ├── settings/                # Settings dialog panels (Account, API Keys, Zendesk, Rate Limits)
│   │   └── zendesk/                 # Zendesk stats component
│   │
│   ├── services/                    # API clients, auth providers, monitoring
│   │   ├── ag-ui/                   # AG-UI streaming client, types, event-types, validators
│   │   ├── api/                     # REST API client, endpoint modules (sessions, models, agents)
│   │   ├── auth/                    # Auth services (local-auth, oauth-config, feedme-auth)
│   │   ├── monitoring/              # Backend health check
│   │   ├── security/                # Admin API config, secure storage, Zendesk admin auth
│   │   ├── storage/                 # Storage service
│   │   └── supabase/                # Supabase clients (browser, server, edge)
│   │
│   ├── state/                       # Zustand stores (FeedMe domain)
│   │   └── stores/
│   │       ├── conversations-store.ts
│   │       ├── folders-store.ts
│   │       ├── realtime-store.ts
│   │       ├── search-store.ts
│   │       ├── analytics-store.ts
│   │       ├── ui-store.ts
│   │       └── store-composition.ts
│   │
│   └── shared/                      # Cross-cutting building blocks
│       ├── components/              # ErrorBoundary, BackendHealthAlert, markdown renderers, VirtualList
│       ├── contexts/                # AuthContext (global auth provider)
│       ├── hooks/                   # useDebounce, usePolling, useWebSocket, useFocusTrap
│       ├── providers/               # QueryProvider (TanStack React Query)
│       ├── ui/                      # shadcn/ui primitives (50+ components)
│       ├── lib/                     # Utilities (environment, debounce, error handling, text)
│       ├── logging/                 # Structured logger, debug logger
│       ├── types/                   # Shared TypeScript types (chat, feedme, logAnalysis)
│       ├── animations/              # Crystalline animation tokens
│       └── design-tokens/           # Crystalline theme CSS
│
├── components/                      # Additional UI components (lamp, aceternity-style effects)
├── scripts/                         # Build/test tooling (check-env, verify-env, test-security)
├── public/                          # Static assets (logos, dock icons)
├── components.json                  # shadcn/ui configuration
├── tailwind.config.ts               # Tailwind configuration
├── vitest.config.ts                 # Vitest test configuration
└── pnpm-lock.yaml                   # Dependency lockfile
```

---

## 3. AG-UI Protocol Integration

Agent Sparrow uses a **native AG-UI protocol** for real-time streaming communication between the frontend and the FastAPI backend. This is a custom SSE-based implementation -- no CopilotKit or GraphQL shim is involved.

### Streaming Endpoint

All chat streaming flows through a single endpoint:

```
POST /api/v1/agui/stream
```

The frontend proxies this via Next.js rewrites configured in `next.config.js`:

```javascript
// frontend/next.config.js
async rewrites() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  return [
    { source: "/api/:path*", destination: `${apiUrl}/api/:path*` },
    { source: "/ws/:path*", destination: `${apiUrl}/ws/:path*` },
  ];
}
```

### Client Architecture

**File**: `frontend/src/services/ag-ui/client.ts`

The `createSparrowAgent()` factory creates a `SparrowAgent` instance that:

1. Maintains local message state and agent configuration.
2. Sends `RunAgentInput` payloads (threadId, runId, state, messages, tools, context) as POST requests.
3. Reads the SSE response body using `ReadableStream` and `TextDecoder`.
4. Parses `data:` lines, dispatching events through handler callbacks.
5. Supports abort via `AbortController` for cancellation.
6. Enforces a 10 MB SSE buffer limit to prevent memory exhaustion.

```typescript
// Key interfaces from frontend/src/services/ag-ui/client.ts
interface SparrowAgent {
  messages: Message[];
  state: Record<string, unknown>;
  addMessage: (message: Message) => void;
  setState: (state: Record<string, unknown>) => void;
  runAgent: (input: Partial<RunAgentInput>, handlers: AgentEventHandlers) => Promise<void>;
  abortRun: () => void;
}

interface AgentEventHandlers {
  signal?: AbortSignal;
  onTextMessageContentEvent?: (params) => void;
  onMessagesChanged?: (params) => void;
  onCustomEvent?: (params) => unknown | Promise<unknown>;
  onStateChanged?: (params) => void;
  onToolCallStartEvent?: (params) => void;
  onToolCallResultEvent?: (params) => void;
  onRunFailed?: (params) => void;
}
```

### SSE Event Types

The client processes these standard AG-UI events (case-insensitive):

| Event Type | Purpose |
|-----------|---------|
| `TEXT_MESSAGE_CONTENT` | Incremental text deltas from the agent |
| `MESSAGES_SNAPSHOT` | Full message list snapshot |
| `CUSTOM` / `on_custom_event` | Custom events (thinking traces, tool evidence, artifacts, subagents) |
| `STATE_SNAPSHOT` | Agent state updates |
| `TOOL_CALL_START` | Tool invocation begins |
| `TOOL_CALL_END` / `TOOL_CALL_RESULT` | Tool invocation completes |
| `RUN_ERROR` | Agent run failure |

### Custom Event Types

**File**: `frontend/src/services/ag-ui/event-types.ts`

Custom events carry domain-specific payloads via a discriminated union:

| Custom Event Name | Payload Type | Purpose |
|------------------|-------------|---------|
| `agent_thinking_trace` | `AgentThinkingTraceEvent` | Thought/action/result steps for the thinking panel |
| `agent_timeline_update` | `AgentTimelineUpdateEvent` | Timeline operations (agent, tool, thought, todo) |
| `tool_evidence_update` | `ToolEvidenceUpdateEvent` | Tool output with evidence cards |
| `agent_todos_update` | `AgentTodosUpdateEvent` | Todo list progress |
| `genui_state_update` | `GenuiStateUpdateEvent` | Generative UI state |
| `image_artifact` | `ImageArtifactEvent` | Image artifacts (URL or base64) |
| `article_artifact` | `ArticleArtifactEvent` | Article markdown artifacts |
| `subagent_spawn` | `SubagentSpawnEvent` | Subagent (research, log diagnoser) started |
| `subagent_end` | `SubagentEndEvent` | Subagent completed or failed |
| `subagent_thinking_delta` | `SubagentThinkingDeltaEvent` | Incremental subagent thinking text |
| `objective_hint_update` | `ObjectiveHintUpdateEvent` | Phase/objective progress hints |

### Runtime Validation

**File**: `frontend/src/services/ag-ui/validators.ts`

Every custom event is validated at runtime using **Zod schemas** before being processed. The `validateCustomEvent(eventName, data)` function routes to the appropriate schema validator and returns `null` for invalid or unknown events. This prevents malformed backend data from crashing the UI.

### Auth Token Handling

The AG-UI client resolves auth tokens in this priority order:

1. Local auth bypass token (when `NEXT_PUBLIC_LOCAL_AUTH_BYPASS=true`)
2. Supabase session access token
3. `localStorage` / `sessionStorage` fallback

Tokens are sent as `Authorization: Bearer <token>` headers on every streaming request.

---

## Additional References

- Runtime and operational details: `docs/frontend-reference.md`
