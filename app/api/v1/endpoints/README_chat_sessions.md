# Chat Session API Documentation

Complete backend implementation for chat session persistence in the MB-Sparrow project.

## Overview

This implementation provides a robust chat session management system with the following features:

- **Session Persistence**: Store and manage chat sessions per user per agent type
- **Message History**: Complete message history with metadata support
- **Multi-Agent Support**: Separate sessions for different agent types (primary, log_analysis, research, router)
- **Automatic Cleanup**: Limit active sessions per user (max 5 per agent type)
- **Authentication**: JWT-based authentication following existing patterns
- **Pagination**: Efficient pagination for sessions and messages
- **Soft Deletion**: Sessions are marked inactive rather than deleted

## Database Schema

### Tables Created

#### `chat_sessions`
- `id`: Primary key
- `user_id`: User identifier from JWT token
- `title`: Session title/topic
- `agent_type`: Type of agent (primary, log_analysis, research, router)
- `created_at`, `last_message_at`, `updated_at`: Timestamps
- `is_active`: Boolean for soft deletion
- `metadata`: JSONB for additional data
- `message_count`: Cached message count

#### `chat_messages`
- `id`: Primary key
- `session_id`: Foreign key to chat_sessions
- `content`: Message content
- `message_type`: user, assistant, or system
- `agent_type`: Agent that generated assistant messages
- `created_at`: Timestamp
- `metadata`: JSONB for additional data

### Constraints & Features
- Max 5 active sessions per user per agent type
- Automatic timestamp updates via triggers
- Foreign key cascading for message deletion
- Optimized indexes for common queries

## API Endpoints

All endpoints require JWT authentication via `Authorization: Bearer <token>` header.

### Chat Sessions

#### `POST /api/v1/chat-sessions`
Create a new chat session.

**Request Body:**
```json
{
  "title": "My Chat Session",
  "agent_type": "primary",
  "metadata": {"key": "value"},
  "is_active": true
}
```

#### `GET /api/v1/chat-sessions`
List chat sessions for the current user.

**Query Parameters:**
- `agent_type`: Filter by agent type
- `is_active`: Filter by active status
- `page`: Page number (default: 1)
- `page_size`: Items per page (default: 10, max: 100)
- `search`: Search in session titles

#### `GET /api/v1/chat-sessions/{session_id}`
Get a specific chat session.

**Query Parameters:**
- `include_messages`: Include messages in response (default: true)

#### `PUT /api/v1/chat-sessions/{session_id}`
Update a chat session.

**Request Body:**
```json
{
  "title": "Updated Title",
  "is_active": false,
  "metadata": {"updated": true}
}
```

#### `DELETE /api/v1/chat-sessions/{session_id}`
Soft delete a chat session (marks as inactive).

### Chat Messages

#### `POST /api/v1/chat-sessions/{session_id}/messages`
Add a message to a session.

**Request Body:**
```json
{
  "content": "Hello, how can you help?",
  "message_type": "user",
  "metadata": {"timestamp": "2024-01-01T00:00:00Z"}
}
```

For assistant messages:
```json
{
  "content": "I can help you with...",
  "message_type": "assistant",
  "agent_type": "primary",
  "metadata": {}
}
```

#### `GET /api/v1/chat-sessions/{session_id}/messages`
List messages for a session.

**Query Parameters:**
- `page`: Page number (default: 1)
- `page_size`: Items per page (default: 50, max: 200)
- `message_type`: Filter by message type

### Statistics

#### `GET /api/v1/chat-sessions/stats/user`
Get chat statistics for the current user.

**Response:**
```json
{
  "user_id": "user123",
  "total_sessions": 10,
  "active_sessions": 3,
  "total_messages": 150,
  "sessions_by_agent_type": {
    "primary": 5,
    "log_analysis": 3,
    "research": 2
  },
  "most_recent_session": "2024-01-01T12:00:00Z",
  "oldest_session": "2023-12-01T10:00:00Z"
}
```

## Configuration

Add to your environment variables:

```bash
# Chat Session Configuration
MAX_SESSIONS_PER_AGENT=5
CHAT_MESSAGE_MAX_LENGTH=10000
CHAT_TITLE_MAX_LENGTH=255
CHAT_SESSION_CLEANUP_DAYS=30
CHAT_ENABLE_MESSAGE_HISTORY=true
CHAT_DEFAULT_PAGE_SIZE=10
CHAT_MAX_PAGE_SIZE=100
```

## Database Migration

Run the migration to create the required tables:

```sql
-- Apply migration 008
\i app/db/migrations/008_create_chat_sessions.sql
```

## Error Handling

The API follows standard HTTP status codes:

- `200`: Success
- `400`: Bad Request (validation errors)
- `401`: Unauthorized (missing/invalid token)
- `404`: Not Found (session/message not found)
- `500`: Internal Server Error

Error responses follow this format:
```json
{
  "detail": "Error message"
}
```

## Integration Notes

- **Authentication**: Uses existing JWT authentication system
- **Database**: Integrates with the unified connection manager
- **Patterns**: Follows FeedMe endpoint patterns for consistency
- **Validation**: Comprehensive Pydantic model validation
- **Performance**: Optimized queries with proper indexing

## Testing

Run the integration tests:

```bash
pytest app/tests/test_chat_sessions_integration.py -v
```

Tests cover:
- All CRUD operations
- Authentication requirements
- Data validation
- Error scenarios
- Multi-user isolation