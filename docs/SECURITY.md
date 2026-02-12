# Security & Configuration

Last updated: 2026-02-12

---

## Environment Variables

- **Never commit secrets** — use `.env.local` (frontend) and `.env` (backend)
- **Validate on startup** — fail fast if required vars missing
- **Use Pydantic BaseSettings** for backend config

```python
# app/core/settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    GOOGLE_API_KEY: str
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str

    class Config:
        env_file = ".env"

settings = Settings()
```

### Required Environment Variables

| Variable | Description | Required By |
|----------|-------------|-------------|
| `SUPABASE_URL` | Supabase project URL | Backend |
| `SUPABASE_ANON_KEY` | Supabase anonymous key | Backend |
| `GOOGLE_API_KEY` | Gemini API key | Backend |
| `TAVILY_API_KEY` | Web search API | Backend |
| `ENABLE_MEMORY_UI_RETRIEVAL` | Enable Memory UI retrieval | Backend |
| `MEMORY_UI_AGENT_ID` | Agent ID for Memory UI | Backend |
| `MEMORY_UI_TENANT_ID` | Tenant ID for Memory UI | Backend |
| `NEXT_PUBLIC_API_URL` | Backend API URL | Frontend |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase URL | Frontend |
| `OPENAI_API_KEY` | OpenAI key for adapter testing | Backend |
| `LANGSMITH_API_KEY` | LangSmith tracing API key | Backend |
| `LANGSMITH_PROJECT` | LangSmith project name | Backend |
| `REDIS_URL` | Redis connection for Celery background tasks | Backend |
| `ZENDESK_DRY_RUN` | Skip real Zendesk note posting when `true` | Backend |
| `API_KEY_ENCRYPTION_SECRET` | Encryption key for API keys (required in prod) | Backend |

---

## Security Checklist

- [ ] No secrets in code or version control
- [ ] Input validation via Pydantic schemas
- [ ] CORS configured for allowed origins only
- [ ] Authentication required for protected endpoints
- [ ] Rate limiting on public endpoints
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention (proper output encoding)

---

## Key Security Patterns

### Feed Me Authorization

- Mutation endpoints use JWT role-claim admin guard (`app/api/v1/endpoints/feedme/auth.py`)
- Read/list/status endpoints remain open
- Upload validates: 10MB limit, PDF-only, SHA-256 duplicate detection

### Zendesk Security

- Only public comments processed — private/internal data never exposed to agent
- Attachment URLs scrubbed from generated content
- PII redaction applied before agent processing
- `ZENDESK_DRY_RUN=true` prevents real note posting in dev

### Memory UI Security

- Asset proxy (`GET /api/v1/memory/assets/{bucket}/{object_path}`) avoids exposing signed Supabase storage URLs
- Admin gating for edit operations
- Reviewer ID validation prevents FK failures on invalid UUIDs

### API Key Encryption

- `API_KEY_ENCRYPTION_SECRET` required in production
- Missing key causes `OSError` in `app/core/encryption.py`
- Never store unencrypted API keys in the database
