# FeedMe v2.0 Setup & Testing Guide

## Overview

This guide walks you through setting up and testing the FeedMe Celery processing pipeline with HTML transcript parsing and Q&A extraction functionality.

## Prerequisites

1. **Python Environment**: Python 3.8+
2. **Redis Server**: For Celery broker
3. **PostgreSQL Database**: With pgvector extension
4. **Environment Variables**: Properly configured

## Step 1: Install Dependencies

```bash
# Install new dependencies
pip install celery[redis]==5.3.4 kombu==5.3.4 beautifulsoup4

# Or install from updated requirements.txt
pip install -r requirements.txt
```

## Step 2: Start Redis Server

Choose one of the following methods:

### Option A: Using Homebrew (macOS)
```bash
brew services start redis
```

### Option B: Using System Package Manager (Linux)
```bash
sudo systemctl start redis
```

### Option C: Using Docker
```bash
docker run -d -p 6379:6379 redis:7-alpine
```

## Step 3: Set Environment Variables

Create or update your `.env` file:

```bash
# Required for FeedMe Celery
FEEDME_ASYNC_PROCESSING=true
FEEDME_HTML_ENABLED=true
FEEDME_CELERY_BROKER=redis://localhost:6379/1
FEEDME_RESULT_BACKEND=redis://localhost:6379/2

# Database (required)
DATABASE_URL=your_database_url_here

# Optional: Gemini API for AI parsing
GEMINI_API_KEY=your_gemini_api_key_here
```

## Step 4: Run Database Migrations

Apply the new migration for temporary examples and approval workflow:

```bash
# Apply the migration (adjust command based on your migration system)
psql $DATABASE_URL -f app/db/migrations/007_feedme_temp_examples.sql
```

## Step 5: Test the Setup

Run the comprehensive test script:

```bash
python test_feedme_celery.py
```

Expected output:
```
🚀 Starting FeedMe Celery Pipeline Tests
==================================================

📋 Running: Module Imports
------------------------------
✅ Celery version: (5, 3, 4, 'final', 0)
✅ Redis client available
✅ BeautifulSoup available
✅ Celery app imported successfully
   Broker: redis://localhost:6379/1
   Backend: redis://localhost:6379/2
✅ HTML parser available
✅ Module Imports: PASSED

📋 Running: Redis Connection
------------------------------
✅ Redis connection successful
✅ Redis Connection: PASSED

📋 Running: HTML Parsing
------------------------------
✅ HTML parsing successful: 4 examples extracted
   Example 1:
     Q: Email not syncing properly. My Gmail account see...
     A: Please try the following steps: Go to Settings...
✅ HTML Parsing: PASSED
```

## Step 6: Start Celery Worker

### Option A: Using the startup script
```bash
./scripts/start-feedme-worker.sh
```

### Option B: Manual startup
```bash
export PYTHONPATH="$(pwd):$PYTHONPATH"
celery -A app.feedme.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --queues=feedme_default,feedme_processing,feedme_embeddings,feedme_parsing,feedme_health
```

### Option C: Using Docker Compose
```bash
docker-compose -f docker-compose.feedme.yml up -d
```

## Step 7: Test HTML File Upload

### Test with Sample HTML File

1. **Upload the sample file** using the API:

```bash
curl -X POST "http://localhost:8000/api/v1/feedme/conversations/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@sample_support_ticket.html" \
  -F "title=Email Sync Support Ticket" \
  -F "auto_process=true"
```

2. **Check processing status**:

```bash
# Get conversation ID from upload response, then:
curl "http://localhost:8000/api/v1/feedme/conversations/{conversation_id}/status"
```

3. **Preview extracted examples**:

```bash
curl "http://localhost:8000/api/v1/feedme/conversations/{conversation_id}/preview-examples"
```

### Expected Processing Flow

1. **Upload** → Status: `pending`
2. **Processing** → Status: `processing` (HTML parsing + Q&A extraction)
3. **Completed** → Status: `completed` (examples in temp table for review)
4. **Preview** → Human agent reviews extracted Q&A pairs
5. **Approval** → Selected examples moved to main table

## Step 8: Test Approval Workflow

### Preview Examples
```bash
curl "http://localhost:8000/api/v1/feedme/conversations/{conversation_id}/preview-examples"
```

### Approve All Examples
```bash
curl -X POST "http://localhost:8000/api/v1/feedme/conversations/{conversation_id}/approve-examples" \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "admin"}'
```

### Approve Selected Examples
```bash
curl -X POST "http://localhost:8000/api/v1/feedme/conversations/{conversation_id}/approve-examples" \
  -H "Content-Type: application/json" \
  -d '{
    "approved_by": "admin",
    "selected_example_ids": [1, 3, 5]
  }'
```

### Reject Examples
```bash
curl -X POST "http://localhost:8000/api/v1/feedme/conversations/{conversation_id}/reject-examples" \
  -H "Content-Type: application/json" \
  -d '{
    "rejected_by": "admin",
    "rejection_reason": "Low quality examples"
  }'
```

## Troubleshooting

### Common Issues

#### 1. ModuleNotFoundError: No module named 'celery'
```bash
pip install celery[redis]==5.3.4
```

#### 2. Redis Connection Error
```bash
# Check if Redis is running
redis-cli ping

# Should return: PONG
```

#### 3. Database Migration Error
```bash
# Check if migration was applied
psql $DATABASE_URL -c "SELECT * FROM feedme_examples_temp LIMIT 1;"
```

#### 4. Celery Worker Not Starting
```bash
# Check logs for errors
celery -A app.feedme.celery_app worker --loglevel=debug
```

#### 5. Tasks Stuck in Pending
```bash
# Check worker availability
celery -A app.feedme.celery_app inspect ping

# Check active tasks
celery -A app.feedme.celery_app inspect active
```

### Monitoring Tools

#### 1. Flower (Celery monitoring)
```bash
# Start Flower
celery -A app.feedme.celery_app flower --port=5555

# Access at: http://localhost:5555
```

#### 2. Redis CLI
```bash
# Monitor Redis activity
redis-cli monitor
```

#### 3. Celery Inspect
```bash
# Check worker stats
celery -A app.feedme.celery_app inspect stats

# Check registered tasks
celery -A app.feedme.celery_app inspect registered
```

## API Endpoints Summary

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/conversations/upload` | POST | Upload HTML/text transcript |
| `/conversations/{id}/status` | GET | Check processing status |
| `/conversations/{id}/preview-examples` | GET | Preview extracted Q&A |
| `/conversations/{id}/approve-examples` | POST | Approve Q&A examples |
| `/conversations/{id}/reject-examples` | POST | Reject Q&A examples |
| `/conversations/{id}/summary` | GET | Get processing summary |

## Key Features Implemented

✅ **HTML Transcript Parsing**: Supports Zendesk, Intercom, Freshdesk, and generic formats  
✅ **Intelligent Q&A Extraction**: Customer questions paired with agent answers  
✅ **Preview & Approval Workflow**: Human review before finalizing examples  
✅ **Confidence Scoring**: Quality assessment for extracted pairs  
✅ **Celery Integration**: Async processing with proper error handling  
✅ **Database Schema**: Temporary tables with approval functions  
✅ **Content Type Detection**: Automatic HTML vs text format detection  
✅ **Comprehensive Testing**: Full test suite for validation  

## Next Steps

1. **Integration Testing**: Test with real HTML files from support systems
2. **Frontend Integration**: Connect preview/approval UI components
3. **Monitoring Setup**: Configure alerts for failed processing
4. **Performance Tuning**: Optimize for larger HTML files
5. **Agent Integration**: Connect approved examples to Primary Agent retrieval

## Success Criteria Verification

- [x] **Celery Processing Works**: Conversations automatically process on upload
- [x] **HTML Parsing**: Extracts Q&A pairs from HTML transcripts  
- [x] **Preview Functionality**: Human agents can preview extracted Q&A
- [x] **Approval Workflow**: Only approved Q&A saved to main database
- [x] **Error Handling**: Robust error recovery and logging
- [x] **Status Tracking**: Clear progression from pending → processing → completed