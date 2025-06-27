# FeedMe v2.0 Deployment Guide

## Phase 2 Completion: Async Processing Pipeline

This guide covers the complete deployment of FeedMe v2.0 with async processing capabilities.

## 🚀 What's New in v2.0

### ✅ Phase 1: Database Unification (COMPLETED)
- **Unified Database**: FeedMe tables migrated to Supabase with pgvector support
- **Advanced Schema**: Versioning, quality scores, usage tracking, and metadata
- **Connection Pooling**: Sophisticated connection manager with health monitoring
- **Performance Optimization**: Indexes, views, and query optimization

### ✅ Phase 2: Async Processing Pipeline (COMPLETED)
- **Celery Integration**: Full async processing with Redis broker
- **Smart Upload Response**: 202 Accepted for async, 200 for sync processing
- **Background Tasks**: Transcript parsing and embedding generation in background
- **Status Polling**: Frontend polls processing status with exponential backoff
- **Task Management**: Queue routing, retry logic, and error handling

## 🏗️ Architecture Overview

```
Upload Request → API Endpoint → Create DB Record → Trigger Celery Task → Return 202
                                      ↓
Frontend polls /status → Task processes transcript → Updates DB → Frontend shows result
```

## 📋 Prerequisites

### Required Services
- **PostgreSQL with pgvector** (Supabase recommended)
- **Redis** (for Celery broker and result backend)
- **Python 3.8+** with dependencies

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:pass@host:port/database

# FeedMe v2.0 Configuration
FEEDME_ENABLED=true
FEEDME_ASYNC_PROCESSING=true
FEEDME_MAX_FILE_SIZE_MB=10
FEEDME_SIMILARITY_THRESHOLD=0.7

# Celery Configuration  
FEEDME_CELERY_BROKER=redis://localhost:6379/1
FEEDME_RESULT_BACKEND=redis://localhost:6379/2

# Redis
REDIS_URL=redis://localhost:6379/0

# AI/ML
GEMINI_API_KEY=your_gemini_api_key
```

## 🚀 Quick Start

### Option 1: Docker Compose (Recommended)

```bash
# Start Redis and Celery worker
docker-compose -f docker-compose.feedme.yml up -d

# Check status
docker-compose -f docker-compose.feedme.yml ps
```

### Option 2: Manual Setup

```bash
# 1. Start Redis
redis-server
# or: brew services start redis  # macOS
# or: sudo systemctl start redis  # Linux

# 2. Start Celery worker
./scripts/start-feedme-worker.sh

# 3. Start your FastAPI application
python -m uvicorn app.main:app --reload
```

## 🔧 Configuration Options

### Async Processing Control
```bash
# Enable/disable async processing
FEEDME_ASYNC_PROCESSING=true|false

# When disabled, uploads return 200 and set status to PENDING
# When enabled, uploads return 202 and start background processing
```

### Performance Tuning
```bash
# Database connections
FEEDME_MIN_DB_CONNECTIONS=2
FEEDME_MAX_DB_CONNECTIONS=20
FEEDME_DB_TIMEOUT=30

# Processing limits
FEEDME_MAX_EXAMPLES_PER_CONVERSATION=20
FEEDME_EMBEDDING_BATCH_SIZE=10

# Quality thresholds
FEEDME_SIMILARITY_THRESHOLD=0.7
FEEDME_QUALITY_THRESHOLD=0.7
```

### Security Settings
```bash
FEEDME_SECURITY_ENABLED=true
FEEDME_RATE_LIMIT_PER_MINUTE=10
FEEDME_VERSION_CONTROL=true
```

## 📊 Monitoring & Health Checks

### Health Check Endpoint
```bash
GET /api/v1/feedme/health
```

Response includes:
- Database connectivity
- Celery worker status  
- Redis connectivity
- Configuration status

### Flower Dashboard (Celery Monitoring)
```bash
# Access at http://localhost:5555 when using docker-compose
# Or start manually:
celery --app=app.feedme.celery_app flower --port=5555
```

### Processing Status
```bash
GET /api/v1/feedme/conversations/{id}/status
```

## 🔄 Processing Pipeline

### 1. Upload Flow
```bash
POST /api/v1/feedme/conversations/upload
Content-Type: multipart/form-data

{
  "title": "Customer Issue #123",
  "transcript_file": <file>,
  "auto_process": true
}
```

**Response (Async Mode)**:
```json
{
  "id": 123,
  "status": 202,
  "processing_status": "processing",
  "message": "Transcript uploaded successfully. Processing started in background.",
  "processing_mode": "async"
}
```

### 2. Status Polling (Frontend)
```javascript
// Frontend polls with exponential backoff
let delay = 1000
while (true) {
  const status = await fetch(`/api/v1/feedme/conversations/${id}/status`)
  if (status.processing_status !== 'processing') break
  
  await new Promise(resolve => setTimeout(resolve, delay))
  delay = Math.min(delay * 2, 10000) // Max 10 seconds
}
```

### 3. Background Processing
1. **Parse Transcript**: Extract Q&A pairs using AI
2. **Generate Embeddings**: Create vector embeddings for similarity search
3. **Update Database**: Store examples with metadata and vectors
4. **Set Completion**: Update status to 'completed' or 'failed'

## 🛠️ Troubleshooting

### Common Issues

#### 1. Celery Worker Not Starting
```bash
# Check Redis connectivity
redis-cli ping

# Check environment variables
echo $FEEDME_CELERY_BROKER
echo $DATABASE_URL

# Check logs
tail -f celery.log
```

#### 2. Database Connection Issues
```bash
# Test database connectivity
python -c "
from app.db.connection_manager import health_check
print(health_check())
"
```

#### 3. Async Processing Not Working
```bash
# Check if async processing is enabled
curl http://localhost:8000/api/v1/feedme/health

# Verify Celery worker is running
celery --app=app.feedme.celery_app status
```

#### 4. Frontend Hanging on "Processing"
- Check if Celery worker is running
- Verify Redis is accessible
- Check task status in Flower dashboard
- Look for errors in Celery logs

### Debug Mode

```bash
# Enable debug logging
export CELERY_LOG_LEVEL=debug
export FEEDME_DEBUG_MODE=true

# Start worker with debug output
python -m app.feedme.celery_app worker --loglevel=debug
```

## 📈 Performance Optimization

### Database Optimization
- **Indexes**: Already optimized for vector similarity search
- **Connection Pooling**: Configured for 2-20 connections
- **Query Optimization**: Uses prepared statements and batch operations

### Celery Optimization
- **Queue Routing**: Separate queues for different task types
- **Concurrency**: 2 workers by default (adjust based on CPU cores)
- **Rate Limiting**: Prevents overwhelming external APIs
- **Task Batching**: Embeddings generated in batches

### Redis Optimization
```bash
# Redis configuration for production
maxmemory 512mb
maxmemory-policy allkeys-lru
appendonly yes
```

## 🔐 Security Considerations

### File Upload Security
- **File Size Limits**: 10MB default (configurable)
- **File Type Validation**: Text files only
- **Content Sanitization**: HTML cleaned before processing
- **Rate Limiting**: 10 uploads per minute per IP

### Database Security
- **Parameterized Queries**: Prevents SQL injection
- **Connection Encryption**: SSL/TLS for database connections
- **Access Control**: JWT-based authentication (planned)

### Processing Security
- **Sandboxed Execution**: Celery workers run in isolated environment
- **No Command Execution**: Safe text processing only
- **Audit Logging**: All operations logged for compliance

## 🚧 Next Phases

### Phase 3: Edit & Version UI (Planned)
- Rich text editor for transcript editing
- Version control for Q&A examples
- Diff visualization for changes
- Reprocessing after edits

### Phase 4: Advanced Features (Planned)
- HTML sanitization for XSS prevention
- Support for more file formats (Outlook, HelpScout)
- AI-powered quality scoring
- Advanced analytics dashboard

## 📞 Support

For issues or questions:
1. Check the health endpoint: `/api/v1/feedme/health`
2. Review Celery logs for task failures
3. Use Flower dashboard for task monitoring
4. Check Redis connectivity and memory usage

---

**FeedMe v2.0** - Async Processing Pipeline Complete ✅