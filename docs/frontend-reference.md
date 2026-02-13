# Frontend Reference

> **Last updated**: 2026-02-12
>
> Companion reference split from `docs/frontend-architecture.md` for implementation-level details.

Use this reference when implementing UI work in specific feature modules, state stores, services, shared UI, route composition, or frontend coding patterns.

---

## 1. Feature Modules

### 1.1 Auth (`src/features/auth/`)

Authentication components and hooks for the login flow.

| Component | File | Purpose |
|----------|------|---------|
| `GoogleLoginForm` | `components/GoogleLoginForm.tsx` | Google OAuth button (via Supabase) |
| `LampSectionHeader` | `components/LampSectionHeader.tsx` | Animated header for login page |
| `LoginForm` | `components/LoginForm.tsx` | Generic login form wrapper |
| `ProtectedRoute` | `components/ProtectedRoute.tsx` | Client-side auth guard component |
| `UserMenu` | `components/UserMenu.tsx` | User avatar dropdown in header |
| `UserProfile` | `components/UserProfile.tsx` | Profile display |
| `LocalDevLoginForm` | `components/LocalDevLoginForm.tsx` | Dev-mode login form |

The global `AuthProvider` lives in `src/shared/contexts/AuthContext.tsx` and provides `useAuth()` with:
- `user`, `isLoading`, `isAuthenticated`
- `loginWithOAuth(provider)`, `logout()`, `refreshToken()`, `updateProfile(data)`

### 1.2 Chat / LibreChat (`src/features/librechat/`)

The main chat interface, styled as a ChatGPT-like UI. This is the most complex feature module.

**Entry point**: `LibreChatClient.tsx` -- dynamically imported by `src/app/chat/page.tsx` with `ssr: false`.

#### Core Components

| Component | File | Purpose |
|----------|------|---------|
| `LibreChatClient` | `LibreChatClient.tsx` | Top-level orchestrator; creates `SparrowAgent`, manages sessions, provider/model selection |
| `AgentProvider` | `AgentContext.tsx` | React Context wrapping the agent; processes SSE events, manages thinking state, handles interrupts |
| `LibreChatView` | `components/LibreChatView.tsx` | Layout shell (sidebar + header + message list + input + artifact panel) |
| `MessageList` | `components/MessageList.tsx` | Scrollable message list with auto-scroll |
| `MessageItem` | `components/MessageItem.tsx` | Individual message rendering (markdown, attachments, thinking panel, feedback) |
| `ChatInput` | `components/ChatInput.tsx` | Message composer with command menu (attachments, web search toggle, expert-mode selector) |
| `Header` | `components/Header.tsx` | Provider/model selection and top-level chat controls |
| `Sidebar` | `components/Sidebar.tsx` | Conversation history sidebar with rename/delete |
| `Landing` | `components/Landing.tsx` | Empty-state landing with suggested prompts |
| `ThinkingPanel` | `components/ThinkingPanel.tsx` | Collapsible panel showing agent reasoning, objectives, evidence |
| `EnhancedMarkdown` | `components/EnhancedMarkdown.tsx` | Rich markdown renderer (code blocks, math, tables, mermaid) |
| `TipTapEditor` | `components/tiptap/TipTapEditor.tsx` | TipTap-based rich text editor for message editing |
| `FeedbackPopover` | `components/FeedbackPopover.tsx` | Thumbs up/down feedback with memory confidence updates |
| `ToolIndicator` | `components/ToolIndicator.tsx` | Active tool call indicators |
| `ResearchProgress` | `components/ResearchProgress.tsx` | Research subagent progress bar |

#### Command Menu and Hard Mode Selector

`ChatInput` now hosts a two-level command menu:
- Primary actions: attach files/photos, web search toggle, expert mode menu.
- Expert mode submenu: `general`, `mailbird_expert`, `research_expert`, `creative_expert`.
- Selection is keyboard/mouse accessible (`Escape` close, outside-click close, ARIA menu roles).

`AgentContext` keeps mode as first-class run/session state:
- `agentMode` + `setAgentMode(...)` in context API.
- Each send operation stamps `agent_mode` into message metadata and AG-UI forwarded props.
- Log attachments do not force mode flips; they only influence backend hinting/subagent behavior inside the selected mode.

`LibreChatClient` persists mode per session:
- Loads mode from session metadata (`metadata.agent_mode`).
- Persists user changes through `sessionsAPI.update(..., { agent_mode, metadata })`.
- Defaults legacy/new sessions to `general`.

#### Artifacts System

The chat supports **artifacts** (images and articles) rendered in a side panel:

- `artifacts/ArtifactPanel.tsx` -- Side panel with tabbed artifact display
- `artifacts/ArtifactContext.tsx` -- Zustand-backed artifact store
- `artifacts/ArticleEditor.tsx` -- TipTap editor for article artifacts
- `artifacts/MermaidEditor.tsx` -- Mermaid diagram viewer
- `artifacts/imageUtils.ts` -- Image URL handling and blob conversion

#### Panel Event Adapter

**File**: `panel-event-adapter.ts`

A sophisticated state machine that transforms heterogeneous AG-UI custom events into a unified `PanelState` data structure for the ThinkingPanel. Key concepts:

- **Lanes**: Primary lane + subagent lanes (dynamically created on subagent spawn)
- **Objectives**: Individual units of work (thought, tool call, todo, error) within each lane
- **Phases**: `plan` -> `gather` -> `execute` -> `synthesize`
- **Batching**: Thought-cadence events are batched at 200ms intervals to reduce render frequency
- **Deduplication**: Event keys are tracked (up to 1200) to prevent duplicate processing
- **Stale fallback**: Running objectives without completion events are marked `unknown` after 30s
- **Incomplete runs**: Connection-exhausted runs can force unresolved objectives to `unknown` for limited-state signaling

The adapter exposes `usePanelEventAdapter()` hook with `panelState`, `applyCustomEvent`, `applyToolCallStart`, `applyToolCallResult`, `syncTodosSnapshot`, and `markRunIncomplete`.

#### Message Flow

1. User types in `ChatInput` and submits.
2. `AgentContext.sendMessage()` adds the user message, resets panel state, and calls `agent.runAgent()`.
3. The `SparrowAgent` POSTs to `/api/v1/agui/stream` with forwarded props including `web_search_mode` and `agent_mode`, then reads the SSE stream.
4. Text deltas accumulate in a buffer and update the assistant message incrementally.
5. Custom events (thinking traces, tool evidence, artifacts) are dispatched to the panel adapter and artifact store.
6. On completion, user and assistant messages are persisted via `sessionsAPI`.
7. Conversation title is auto-named from the first user message.

### 1.3 FeedMe (`src/features/feedme/`)

Document ingestion and transcript management system with a macOS Dock-style navigation.

**Entry point**: `src/app/feedme/page.tsx` -- renders a full-screen page with animated logo, Dock navigation, and modal dialogs.

| Component | File | Purpose |
|----------|------|---------|
| `Dock` | `components/Dock.tsx` | macOS-style magnifying dock with spring animations |
| `EnhancedAnimatedLogo` | `components/EnhancedAnimatedLogo.tsx` | Multi-frame animated FeedMe logo |
| `FoldersDialog` | `components/FoldersDialog.tsx` | Folder management dialog with drag-and-drop |
| `FolderConversationsDialog` | `components/FolderConversationsDialog.tsx` | Conversations within a specific folder |
| `UploadDialog` | `components/UploadDialog.tsx` | PDF upload dialog with duplicate detection |
| `UnassignedDialog` | `components/UnassignedDialog.tsx` | Unassigned conversations queue |
| `StatsPopover` | `components/StatsPopover.tsx` | Analytics popover (queue depth, latency, OS distribution) |
| `ConversationSidebar` | `components/ConversationSidebar.tsx` | Sidebar note editor with autosave |
| `UnifiedTextCanvas` | `components/UnifiedTextCanvas.tsx` | Main content editor for conversations |
| `PlatformTagSelector` | `components/PlatformTagSelector.tsx` | OS/platform tag assignment |
| `EnhancedFeedMeModal` | `components/EnhancedFeedMeModal.tsx` | Detailed conversation modal |
| `StatsCards` | `components/stats/StatsCards.tsx` | Statistics card components |

**API Client**: `services/feedme-api.ts` -- typed REST client for all FeedMe endpoints with auth headers on mutation calls.

FeedMe state is managed by the Zustand stores in `src/state/stores/` (see [State Management](#5-state-management)).

### 1.4 Memory (`src/features/memory/`)

3D knowledge graph visualization and memory management using react-three-fiber.

**Entry point**: `src/app/memory/page.tsx` -- dynamically imports `MemoryClient` with `ssr: false`.

| Component | File | Purpose |
|----------|------|---------|
| `MemoryClient` | `components/MemoryClient.tsx` | Top-level orchestrator with graph/table/duplicates views |
| `MemoryGraph` | `components/MemoryGraph.tsx` | 3D graph visualization entry (lazy loaded) |
| `MemoryTree3D` | `components/MemoryTree3D.tsx` | Three.js tree scene with spatial clustering |
| `TreeScene` | `components/TreeScene.tsx` | Canvas scene setup with camera, controls, lighting |
| `TreeNode` | `components/TreeNode.tsx` | Individual 3D node with LOD and interaction |
| `TreeBranch` | `components/TreeBranch.tsx` | Branch geometry connecting nodes |
| `TreeTrunk` | `components/TreeTrunk.tsx` | Central trunk geometry |
| `MemoryTable` | `components/MemoryTable.tsx` | Tabular memory view with inline editing |
| `MemoryForm` | `components/MemoryForm.tsx` | Create/edit memory form |
| `MemoryTipTapEditor` | `components/MemoryTipTapEditor.tsx` | TipTap editor for memory content with image resize |
| `MemorySearch` | `components/MemorySearch.tsx` | Semantic search across memories |
| `DuplicateReview` | `components/DuplicateReview.tsx` | Duplicate detection and merge UI |
| `ConfidenceBadge` | `components/ConfidenceBadge.tsx` | Confidence percentage display |
| `RelationshipEditor` | `components/RelationshipEditor.tsx` | Entity relationship editor |

**Supporting Libraries**:
- `lib/api.ts` -- Memory API client (CRUD, search, feedback, import)
- `lib/treeTransform.ts` -- Transforms flat memory data into 3D tree layout
- `lib/spatialClustering.ts` -- Spatial clustering algorithm for node placement
- `lib/cycleDetection.ts` -- Cycle detection in relationship graphs
- `hooks/useMemoryData.ts` -- React Query hooks for memory data fetching
- `hooks/useTree3DLayout.ts` -- 3D layout computation hook
- `hooks/useLOD.ts` -- Level-of-detail management for performance
- `tiptap/MemoryImageExtension.tsx` -- Custom TipTap extension for inline image resize

### 1.5 Settings (`src/features/settings/`)

Settings are rendered in a dialog (not a separate route) triggered from the header.

| Component | File | Purpose |
|----------|------|---------|
| `SettingsDialogV2` | `components/SettingsDialogV2.tsx` | Tabbed settings dialog |
| `GeneralPanel` | `components/panels/GeneralPanel.tsx` | General app settings |
| `AccountPanel` | `components/panels/AccountPanel.tsx` | Account/profile management |
| `APIKeysPanel` | `components/panels/APIKeysPanel.tsx` | API key management |
| `RateLimitsPanel` | `components/panels/RateLimitsPanel.tsx` | Rate limit visualization |
| `ZendeskPanel` | `components/panels/ZendeskPanel.tsx` | Zendesk integration toggle and health |

Legacy `/settings/*` routes are redirected to the dialog via middleware query parameters.

### 1.6 Zendesk (`src/features/zendesk/`)

Minimal frontend surface for Zendesk integration.

| Component | File | Purpose |
|----------|------|---------|
| `ZendeskStats` | `components/ZendeskStats.tsx` | Zendesk queue/usage statistics display |

The Zendesk admin panel is in `src/features/settings/components/panels/ZendeskPanel.tsx`. Backend configuration details are documented in `CLAUDE.md` and `docs/zendesk.md`.

---

## 2. State Management

### Architecture

The frontend uses two complementary state management approaches:

1. **Zustand** -- Client-side domain stores for FeedMe, plus the `AgentContext` for chat state.
2. **TanStack React Query** -- Server-state caching and synchronization for Memory UI data.
3. **React Context** -- Auth state (`AuthProvider`), agent state (`AgentProvider`), artifact state (`ArtifactProvider`).

### Zustand Stores (FeedMe Domain)

All stores are in `frontend/src/state/stores/` and use `devtools` + `subscribeWithSelector` middleware.

| Store | File | Manages |
|-------|------|---------|
| **Conversations** | `conversations-store.ts` | FeedMe conversation CRUD, upload workflows, processing status, examples, selection, approval workflows, bulk operations, caching |
| **Folders** | `folders-store.ts` | Folder hierarchy, drag-and-drop state, folder CRUD, conversation assignment |
| **Realtime** | `realtime-store.ts` | WebSocket connections with auto-reconnect, exponential backoff, processing notifications |
| **Search** | `search-store.ts` | Full-text search with filters (date, tags, confidence, platform), search history, saved searches |
| **Analytics** | `analytics-store.ts` | Performance metrics, usage stats, approval workflow stats |
| **UI** | `ui-store.ts` | Tabs, panels, view modes, modals, sidebar, bulk actions, notifications, theme, keyboard navigation. Persisted via `persist` middleware. |

### Store Composition

**File**: `store-composition.ts`

Cross-store coordination is handled through:

- **`StoreEventBus`** -- Pub/sub event bus for decoupled cross-store communication (e.g., `processing_completed`, `folder_updated`, `search_performed`).
- **`useStoreSync()`** -- Hook that wires up event subscriptions between stores.
- **`useStoreInitialization()`** -- Hook that loads initial data from all stores in parallel and connects WebSocket.
- **Composite hooks** -- `useConversationManagement()`, `useFolderManagement()`, `useSearchIntegration()`, `useBulkOperations()` combine multiple stores for complex operations.

### Chat State (AgentContext)

**File**: `frontend/src/features/librechat/AgentContext.tsx`

The `AgentProvider` React Context manages all chat-related state:

- Messages array and streaming state
- Active tools, thinking traces, and panel state (via `usePanelEventAdapter`)
- Subagent runs and thinking deltas
- Interrupt handling (human-in-the-loop)
- Research progress tracking
- Artifact management
- Web search mode
- Session persistence callbacks
- Todo items

This is separate from Zustand because chat state is tightly coupled to the SSE streaming lifecycle and requires React Context for tree-scoped access.

### Memory UI State

The Memory UI uses **TanStack React Query** hooks (`frontend/src/features/memory/hooks/`) for data fetching and caching, avoiding Zustand for server-state synchronization. Local UI state (view mode, filters, selected items) uses `useState`.

---

## 3. Services Layer

### 3.1 AG-UI Service (`src/services/ag-ui/`)

| File | Purpose |
|------|---------|
| `client.ts` | `createSparrowAgent()` factory, auth token resolution, SSE stream reading/event processing, AG-UI state initialization (`agent_mode`, `web_search_mode`) |
| `types.ts` | `AttachmentInput`, `BinaryInputContent`, `TextInputContent`, `InterruptPayload`, `AgentState`, content creation helpers |
| `event-types.ts` | TypeScript types for all custom events, `AgentCustomEvent` discriminated union, `KNOWN_EVENT_NAMES`, type guards |
| `validators.ts` | Zod schemas for runtime validation of all custom event payloads, `validateCustomEvent()` router |
| `validators.test.ts` | Test suite for event validators |

### 3.2 REST API Client (`src/services/api/`)

| File | Purpose |
|------|---------|
| `api-client.ts` | Centralized HTTP client with auth header injection, error handling, SSE support |
| `api-monitor.ts` | API latency/status metrics collection, slow request warnings |
| `api-request-manager.ts` | Request deduplication and lifecycle management |
| `api.ts` | Base API configuration |
| `api-keys.ts` | API key management client |
| `endpoints/sessions.ts` | Chat session CRUD plus per-session mode persistence (`agent_mode`) |
| `endpoints/models.ts` | Model registry/provider availability; sends `agent_mode` with model-list requests |
| `endpoints/agents.ts` | Agent endpoint client |
| `endpoints/rateLimitApi.ts` | Rate limit status/metrics client |
| `endpoints/metadata.ts` | Metadata/link preview client |
| `endpoints/api-key-service-secure.ts` | Secure API key service |

### 3.3 Auth Services (`src/services/auth/`)

| File | Purpose |
|------|---------|
| `local-auth.ts` | Local development auth bypass (provisions JWT via `/api/v1/auth/local-signin`) |
| `oauth-config.ts` | OAuth provider configuration |
| `providers/feedme-auth.ts` | FeedMe-specific auth provider for WebSocket authentication |

### 3.4 Supabase Clients (`src/services/supabase/`)

Three Supabase client variants for different runtime contexts:

| File | Runtime | Purpose |
|------|---------|---------|
| `browser-client.ts` | Client-side | Browser Supabase client (used by components, auth) |
| `server-client.ts` | Server-side | Server-component Supabase client |
| `edge-client.ts` | Edge Runtime | Middleware-compatible Supabase client for auth checks |

### 3.5 Security Services (`src/services/security/`)

| File | Purpose |
|------|---------|
| `modules/secure-storage.ts` | Encrypted local/session storage with integrity checks |
| `admin-api-config.ts` | Admin API proxy configuration |
| `zendesk-admin-auth.ts` | Zendesk admin email/role validation |

### 3.6 Monitoring (`src/services/monitoring/`)

| File | Purpose |
|------|---------|
| `backend-health-check.ts` | Backend connectivity monitoring with health endpoint polling |

---

## 4. Shared Components

### shadcn/ui Primitives (`src/shared/ui/`)

Over 50 Radix UI-based components are available, installed via shadcn/ui:

Accordion, AlertDialog, Alert, AspectRatio, Avatar, Badge, Breadcrumb, Button, Calendar, Card, Carousel, Chart, Checkbox, Collapsible, Command, ContextMenu, DateRangePicker, Dialog, Drawer, DropdownMenu, Form, HoverCard, Input, InputOTP, Label, Menubar, NavigationMenu, Pagination, Popover, PopoverForm, Progress, RadioGroup, Resizable, ScrollArea, Select, Separator, Sheet, Sidebar, Skeleton, Slider, Sonner (toaster), Switch, Table, Tabs, Textarea, Toast, Toggle, ToggleGroup, Tooltip.

Custom UI additions: `FeedMeButton`, `FolderIcon`, `GlowingEffect`, `LightDarkToggle`, `SettingsButtonV2`, `UserAvatar`.

### Custom Shared Components (`src/shared/components/`)

| Component | File | Purpose |
|----------|------|---------|
| `ErrorBoundary` | `ErrorBoundary.tsx` | Global error boundary with recovery |
| `UnifiedErrorBoundary` | `error/UnifiedErrorBoundary.tsx` | Enhanced error boundary |
| `BackendHealthAlert` | `BackendHealthAlert.tsx` | User-facing backend connectivity alert |
| `ChunkErrorRecovery` | `utils/ChunkErrorRecovery.tsx` | Next.js chunk loading error recovery |
| `ShinyText` | `ShinyText.tsx` | Gradient text animation |
| `VirtualList` | `virtualization/VirtualList.tsx` | Virtual scrolling wrapper |
| `MarkdownMessage` | `markdown/MarkdownMessage.tsx` | Markdown renderer |
| `ExecutiveSummaryRenderer` | `markdown/ExecutiveSummaryRenderer.tsx` | Executive summary display |
| `Header` | `layout/Header.tsx` | Shared layout header |
| `UserPanel` | `layout/UserPanel.tsx` | User profile panel |
| `DevModeIndicator` | `dev/DevModeIndicator.tsx` | Development mode indicator |

### Shared Hooks (`src/shared/hooks/`)

| Hook | Purpose |
|------|---------|
| `useDebounce` | Debounce values |
| `usePolling` | Interval-based polling with cleanup |
| `useWebSocket` | WebSocket connection management |
| `useFocusTrap` | Accessibility focus trapping |
| `useOutsideClick` | Click-outside detection |
| `useApiErrorHandler` | Centralized API error handling |
| `useToast` | Toast notification hook |

### Shared Logging (`src/shared/logging/`)

| Module | Purpose |
|--------|---------|
| `logger.ts` | Structured logger with dev-friendly formatting and production fallbacks |
| `debug-logger.ts` | Debug-mode logger with configurable channels |

---

## 5. Routing and Layouts

### App Router Structure

The application uses Next.js 16 App Router with the following route hierarchy:

| Route | Page | Auth Required | Description |
|-------|------|---------------|-------------|
| `/` | `page.tsx` | Yes | Redirects to `/chat` |
| `/chat` | `chat/page.tsx` | Yes | Main chat interface (LibreChat) |
| `/feedme` | `feedme/page.tsx` | Yes | FeedMe document hub |
| `/feedme/conversation/[id]` | `feedme/conversation/[id]/page.tsx` | Yes | Individual conversation view |
| `/memory` | `memory/page.tsx` | Yes | 3D knowledge graph |
| `/login` | `login/page.tsx` | No | OAuth login |
| `/auth/callback` | `auth/callback/page.tsx` | No | Supabase OAuth callback |

### Root Layout (`src/app/layout.tsx`)

The root layout wraps the entire application with:

1. **Google Fonts**: Lora (serif) + Inter (sans-serif) via `next/font/google`
2. **ThemeProvider** (`next-themes`): Dark/light/system mode, dark by default
3. **QueryProvider** (`@tanstack/react-query`): React Query client with 30s stale time
4. **AuthProvider**: Global auth state via Supabase
5. **ChunkErrorRecovery**: Handles chunk loading failures gracefully
6. **Toaster** (Sonner): Global toast notifications
7. **KaTeX CSS**: Loaded via CDN for math rendering
8. **Grammarly suppression**: Prevents Grammarly from interfering with text inputs

### Middleware (`frontend/middleware.ts`)

The Edge Runtime middleware handles:

1. **Settings route consolidation**: Legacy `/settings/*` routes redirect to `/?settings=<tab>`.
2. **Static file bypass**: `/_next`, `/static`, and files with extensions skip middleware.
3. **Local auth bypass**: When `NEXT_PUBLIC_LOCAL_AUTH_BYPASS=true`, non-API routes pass through without auth checks.
4. **Supabase auth validation**: Uses the Edge-compatible Supabase client to verify the user session.
5. **Unauthenticated redirect**: Non-public routes redirect to `/login?returnUrl=<encoded-path>`.
6. **Auth route redirect**: Already-authenticated users on `/login` redirect to `/`.

**Public routes**: `/login`, `/auth/callback`, `/api/health`

**Matcher**: All paths except `_next/static`, `_next/image`, `favicon.ico`, and files with extensions.

### Next.js Configuration (`next.config.js`)

- **Turbopack**: Enabled as the default bundler (Next.js 16).
- **Webpack fallback**: Used only for the KaTeX CSS stub alias.
- **TypeScript**: `ignoreBuildErrors: true` (build proceeds despite type errors).
- **API rewrites**: Proxies `/api/*` and `/ws/*` to the backend.
- **Security headers**: CSP, X-Frame-Options (DENY), X-Content-Type-Options (nosniff), Referrer-Policy, Permissions-Policy, HSTS (production only).
- **Powered-by header**: Disabled for security.

---

## 6. Key Patterns

### Component Composition

The chat interface uses a layered composition pattern:

```
ChatPage (dynamic import, ssr: false)
  └── LibreChatClient (agent creation, session management)
        └── ArtifactProvider (artifact state)
              └── AgentProvider (SSE event processing, message state)
                    └── LibreChatView (layout)
                          ├── Sidebar (conversation list)
                          ├── Header (model selector, toggles)
                          ├── MessageList
                          │     └── MessageItem[] (markdown, thinking panel, feedback)
                          ├── ChatInput (composer)
                          └── ArtifactPanel (side panel)
```

### Dynamic Imports

Heavy components are loaded dynamically with `ssr: false` to avoid server-side rendering issues and reduce initial bundle size:

```typescript
// Chat page
const LibreChatClient = dynamic(() => import("@/features/librechat/LibreChatClient"), { ssr: false });

// Memory page
const MemoryClient = dynamic(() => import("@/features/memory/components/MemoryClient"), { ssr: false });

// Inside MemoryClient
const MemoryGraph = React.lazy(() => import("./MemoryGraph"));
const MemoryTable = React.lazy(() => import("./MemoryTable"));

// Inside MessageItem
const TipTapEditor = dynamic(() => import("./tiptap/TipTapEditor").then(mod => mod.TipTapEditor), { ssr: false });
```

### Hooks Pattern

Feature-specific hooks encapsulate data fetching, state management, and side effects:

```typescript
// Memory UI uses React Query hooks
const { data, isLoading } = useMemoryMe(filters);
const { data: stats } = useMemoryStats();
const importMutation = useImportZendeskTagged();

// FeedMe uses Zustand selector hooks
const conversations = useConversations();
const { loadConversations, uploadConversation } = useConversationsActions();

// Chat uses AgentContext
const { messages, isStreaming, sendMessage, error, panelState } = useAgent();
```

### Error Handling

Errors are handled at multiple levels:

1. **Error Boundaries**: `ErrorBoundary`, `GraphErrorBoundary`, `DialogErrorBoundary`, `UnifiedErrorBoundary` catch React rendering errors.
2. **API Error Handler**: `useApiErrorHandler()` hook provides centralized API error handling with toast notifications.
3. **Optimistic Updates**: Zustand stores perform optimistic updates and revert on API failure.
4. **SSE Error Handling**: The AG-UI client catches `RUN_ERROR` events and non-abort fetch errors, routing them to `onRunFailed` handlers.
5. **Validation**: Zod validators on incoming events prevent malformed data from propagating.
6. **Superseded Request Detection**: `isSupersededRequestError` prevents intentional abort/replacement events from surfacing as errors.

### Streaming Pattern

The streaming architecture follows this pattern:

1. **Agent Creation**: `createSparrowAgent(config)` sets up the connection configuration.
2. **Message Sending**: `agent.runAgent(input, handlers)` posts to `/api/v1/agui/stream`.
3. **Stream Reading**: `ReadableStream` reader processes chunks, splits on newlines, parses JSON.
4. **Event Dispatch**: Each parsed event is routed to the appropriate handler callback.
5. **Panel State**: Custom events flow through `usePanelEventAdapter` which batches and deduplicates before updating the thinking panel.
6. **Persistence**: On stream completion, messages are persisted to the backend via `sessionsAPI`.

### TypeScript Path Aliases

Configured in `tsconfig.json` for clean imports:

```json
{
  "@/*": ["./src/*"],
  "@/app/*": ["./src/app/*"],
  "@/features/*": ["./src/features/*"],
  "@/shared/*": ["./src/shared/*"],
  "@/services/*": ["./src/services/*"],
  "@/state/*": ["./src/state/*"]
}
```

---

## Cross-References

- Backend architecture: `docs/backend-architecture.md`
- Coding standards: `docs/CODING_STANDARDS.md`
- Testing guidelines: `docs/TESTING.md`
- FeedMe hardening details: `docs/feedme-hardening-notes.md`
- Memory UI: `docs/memory-ui.md`
- Zendesk integration: `docs/zendesk.md`
- Model configuration: `CLAUDE.md` (Model Configuration section)
- Development commands: `docs/DEVELOPMENT.md`
