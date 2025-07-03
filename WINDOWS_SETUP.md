# MB-Sparrow Windows Setup Guide

## Prerequisites

### Required Software
1. **Python 3.10+** - Download from [python.org](https://www.python.org/downloads/)
   - ✅ Enable "Add Python to PATH" during installation
   - ✅ Verify: `python --version`

2. **Node.js 18+** - Download from [nodejs.org](https://nodejs.org/)
   - ✅ Verify: `node --version` and `npm --version`

3. **Redis** (for FeedMe background processing)
   - **Option A**: Download Windows Redis from [github.com/tporadowski/redis](https://github.com/tporadowski/redis/releases)
   - **Option B**: Use Docker: `docker run --name redis -p 6379:6379 -d redis`
   - ✅ Verify: `redis-cli ping` (should return PONG)

4. **Git** - Download from [git-scm.com](https://git-scm.com/download/win)

### Environment Variables
Ensure you have a `.env` file with required configuration:
```bash
# Copy .env.example to .env and configure:
GEMINI_API_KEY=your_google_ai_api_key_here
FEEDME_ENABLED=true
REDIS_URL=redis://localhost:6379/0
```

## Quick Start

### 1. Clone and Setup
```cmd
git clone <repository-url>
cd MB-Sparrow-main
```

### 2. Start System
```cmd
start_system.bat
```

The script will automatically:
- ✅ Create Python virtual environment
- ✅ Install all dependencies (including google-generativeai fix)
- ✅ Start Backend (FastAPI) on port 8000
- ✅ Start Frontend (Next.js) on port 3000
- ✅ Start FeedMe Celery worker (if Redis available)
- ✅ Verify all services are running

### 3. Access Application
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **FeedMe v2.0**: http://localhost:3000/feedme

### 4. Stop System
```cmd
stop_system.bat
```

## Troubleshooting

### Common Issues

#### 1. "Python not found"
- Reinstall Python with "Add to PATH" option
- Or manually add Python to PATH: `C:\Python310\Scripts\;C:\Python310\`

#### 2. "Node.js not found"
- Reinstall Node.js from nodejs.org
- Restart Command Prompt after installation

#### 3. "Redis connection failed"
- Install Redis for Windows or use Docker
- Start Redis service: `redis-server`
- FeedMe will work without Redis but background processing will be disabled

#### 4. "Port already in use"
- The script automatically kills existing processes
- If manual intervention needed: use Task Manager to end processes

#### 5. "google.generativeai import error"
- The script automatically installs missing dependencies
- If issue persists: `pip install google-generativeai`

#### 6. "Permission denied" errors
- Run Command Prompt as Administrator
- Check Windows Defender/Antivirus isn't blocking Python

### Dependency Conflicts
The script handles known dependency conflicts between:
- `google-generativeai` and `google-ai-generativelanguage`
- `langchain-google-genai` compatibility

Warning messages about these conflicts are expected and can be ignored.

## Manual Installation

If the automated script fails, you can install manually:

```cmd
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start services separately
# Terminal 1: Backend
uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm install --legacy-peer-deps
npm run dev

# Terminal 3: Celery Worker (optional)
python -m celery -A app.feedme.celery_app worker --loglevel=info
```

## Performance Optimization

### For Development
- Use SSD for better file I/O performance
- 8GB+ RAM recommended for smooth operation
- Close unnecessary applications to free resources

### For Production
- Consider using Redis Cluster for scaling
- Use production WSGI server instead of uvicorn --reload
- Implement proper logging and monitoring

## Security Notes

- **API Keys**: Never commit `.env` file to version control
- **Firewall**: Consider restricting access to ports 8000/3000 if needed
- **Updates**: Keep Python, Node.js, and dependencies updated

## Development Tips

### Viewing Logs
```cmd
# PowerShell (recommended)
Get-Content -Wait system_logs\backend\backend.log
Get-Content -Wait system_logs\frontend\frontend.log
Get-Content -Wait system_logs\celery\celery_worker.log

# Command Prompt
type system_logs\backend\backend.log
```

### Database Operations
```cmd
# Access PostgreSQL (if using)
psql -h localhost -U postgres -d mb_sparrow

# Redis CLI
redis-cli
```

### Testing
```cmd
# Run Python tests
pytest

# Run frontend tests
cd frontend
npm test
```

---

For additional support, check the main project documentation or create an issue in the repository.