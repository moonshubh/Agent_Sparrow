# MB-Sparrow Windows Setup Guide

## Complete Windows Installation & Setup Instructions

This guide provides step-by-step instructions for setting up the MB-Sparrow multi-agent AI system on Windows. The system consists of a FastAPI backend with multiple AI agents and a Next.js frontend with modern UI components.

---

## 📋 Table of Contents

1. [Prerequisites & Environment Setup](#prerequisites--environment-setup)
2. [Repository Setup](#repository-setup)
3. [Environment Configuration](#environment-configuration)
4. [Backend Setup](#backend-setup)
5. [Frontend Setup](#frontend-setup)
6. [Testing & Verification](#testing--verification)
7. [Troubleshooting](#troubleshooting)
8. [Usage Guide](#usage-guide)
9. [System Architecture](#system-architecture)

---

## 🛠️ Prerequisites & Environment Setup

### System Requirements
- **Operating System**: Windows 10 (version 2004+) or Windows 11
- **Memory**: 8GB RAM minimum (16GB recommended)
- **Storage**: 5GB free space
- **Internet**: Stable internet connection for API calls

### 1. Install Python 3.11+

**Option A: Microsoft Store (Recommended for Beginners)**
1. Open Microsoft Store
2. Search for "Python 3.11"
3. Click "Install" - this automatically handles PATH setup

**Option B: Official Python.org Installer**
1. Visit [python.org/downloads](https://www.python.org/downloads/)
2. Download Python 3.11.x (latest stable version)
3. Run the installer
4. **⚠️ CRITICAL**: Check "Add Python to PATH" during installation
5. Choose "Customize installation" and ensure "pip" is included

**Verify Installation:**
```powershell
python --version
pip --version
```

### 2. Install Node.js 18+

**Option A: NVM for Windows (Recommended)**
1. Visit [nvm-windows GitHub releases](https://github.com/coreybutler/nvm-windows/releases)
2. Download and run `nvm-setup.exe`
3. Open PowerShell as Administrator and run:
```powershell
nvm install 18
nvm use 18
```

**Option B: Official Node.js Installer**
1. Visit [nodejs.org](https://nodejs.org/)
2. Download the LTS version (18.x or higher)
3. Run the installer with default settings

**Verify Installation:**
```powershell
node --version
npm --version
```

### 3. Install Git for Windows

1. Download from [git-scm.com](https://git-scm.com/download/win)
2. Run installer with default settings
3. Verify: `git --version`

### 4. Install Redis

**Option A: Using WSL2 (Recommended)**
1. Enable WSL2 in Windows Features:
   ```powershell
   # Run as Administrator
   wsl --install
   ```
2. Restart your computer
3. Install Ubuntu from Microsoft Store
4. In Ubuntu terminal:
   ```bash
   sudo apt update
   sudo apt install redis-server
   sudo service redis-server start
   ```

**Option B: Docker (Alternative)**
1. Install Docker Desktop for Windows
2. Run Redis container:
   ```powershell
   docker run -d -p 6379:6379 --name redis redis:latest
   ```

**Option C: Cloud Redis (Easiest)**
- Use Redis Cloud, Upstash, or similar service
- Get connection URL for configuration

**Verify Redis:**
```powershell
# If using WSL2
wsl redis-cli ping
# Should return "PONG"

# If using Docker
docker exec redis redis-cli ping
```

---

## 📁 Repository Setup

### 1. Clone the Repository

```powershell
cd C:\
mkdir Development
cd Development
git clone https://github.com/your-username/MB-Sparrow.git
cd MB-Sparrow
```

### 2. Directory Structure Overview

```
MB-Sparrow/
├── app/                    # FastAPI Backend
│   ├── agents_v2/         # AI Agent Implementations
│   ├── api/               # REST API Endpoints
│   ├── core/              # Core Settings & Config
│   └── main.py            # FastAPI Application Entry
├── frontend/              # Next.js Frontend
│   ├── app/               # Next.js App Router
│   ├── components/        # React Components
│   └── package.json       # Frontend Dependencies
├── requirements.txt       # Python Dependencies
└── README.md             # This file
```

---

## ⚙️ Environment Configuration

### 1. Backend Environment Variables

Create `.env` file in the project root:

```powershell
# In project root directory
New-Item -Path ".env" -ItemType File
notepad .env
```

**Complete .env Configuration:**

```env
# API Keys (REQUIRED)
GEMINI_API_KEY=your_gemini_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here

# Database Configuration (REQUIRED)
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
DATABASE_URL=postgresql://username:password@hostname:port/database_name

# Redis Configuration
REDIS_URL=redis://localhost:6379
RATE_LIMIT_REDIS_URL=redis://localhost:6379
RATE_LIMIT_REDIS_DB=3

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

# Rate Limiting (Free Tier Safe)
GEMINI_FLASH_RPM_LIMIT=8
GEMINI_FLASH_RPD_LIMIT=200
GEMINI_PRO_RPM_LIMIT=4
GEMINI_PRO_RPD_LIMIT=80

# Performance Settings
OPTIMIZATION_THRESHOLD_LINES=500
USE_OPTIMIZED_ANALYSIS=true
ENABLE_ML_PATTERN_DISCOVERY=true
ENABLE_PREDICTIVE_ANALYSIS=true
ENABLE_CORRELATION_ANALYSIS=true
ENABLE_AUTOMATED_REMEDIATION=false
ENABLE_CROSS_PLATFORM_SUPPORT=true
ENABLE_MULTI_LANGUAGE_SUPPORT=true
ML_CONFIDENCE_THRESHOLD=0.85
CORRELATION_THRESHOLD=0.7

# Security Settings
FEEDME_SECURITY_ENABLED=true
FEEDME_RATE_LIMIT_PER_MINUTE=10
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT=60
```

### 2. Frontend Environment Variables

Create `frontend/.env.local`:

```powershell
cd frontend
New-Item -Path ".env.local" -ItemType File
notepad .env.local
```

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_FRONTEND_URL=http://localhost:3000
NEXT_PUBLIC_FEEDME_ENABLED=true
```

### 3. API Keys Setup

**Google Gemini API Key:**
1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Add to `.env` as `GEMINI_API_KEY`

**Tavily API Key (for Research Agent):**
1. Visit [Tavily API](https://tavily.com/)
2. Sign up and get API key
3. Add to `.env` as `TAVILY_API_KEY`

**Supabase Setup:**
1. Visit [supabase.com](https://supabase.com/)
2. Create a new project
3. Go to Settings → API to get URL and anon key
4. Go to Settings → Database to get connection string
5. Add to `.env` as shown above

---

## 🔧 Backend Setup

### 1. Create Virtual Environment

```powershell
# In project root directory
python -m venv venv

# Activate virtual environment
venv\Scripts\activate

# Your prompt should now show (venv)
```

### 2. Install Python Dependencies

```powershell
# Ensure you're in the virtual environment
pip install --upgrade pip
pip install -r requirements.txt
```

**If you encounter issues with torch:**
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

### 3. Database Setup

**Run Migrations:**
```powershell
# Ensure your Supabase database is accessible
python -c "from app.db.connection_manager import get_connection; print('Database connection test:', get_connection() is not None)"
```

**Initialize Database Tables:**
The system will automatically create required tables on first run, but you can manually run migrations:

```powershell
# Check if migrations need to be run
python -c "from app.db import connection_manager; connection_manager.init_database()"
```

### 4. Start the Backend Server

```powershell
# Make sure virtual environment is activated
cd app
python main.py
```

**Alternative using uvicorn directly:**
```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Verify Backend is Running:**
- Open browser to `http://localhost:8000`
- You should see "MB-Sparrow API is running!"
- Check API docs at `http://localhost:8000/docs`

---

## 🎨 Frontend Setup

### 1. Install Dependencies

```powershell
cd frontend
npm install
```

**If you encounter permission errors:**
```powershell
npm install --no-optional
```

### 2. Start Development Server

```powershell
npm run dev
```

**Verify Frontend is Running:**
- Open browser to `http://localhost:3000`
- You should see the MB-Sparrow welcome interface

### 3. Build Production Version (Optional)

```powershell
npm run build
npm start
```

---

## ✅ Testing & Verification

### 1. System Health Check

**Backend Health:**
```powershell
# Test API endpoint
curl http://localhost:8000/health
# Or visit in browser
```

**Frontend Health:**
```powershell
# Test frontend connectivity
curl http://localhost:3000
```

### 2. Agent Testing

**Test Primary Agent:**
1. Open `http://localhost:3000`
2. Type: "Hello, can you help me with email setup?"
3. Verify you get a structured response

**Test Enhanced Log Analysis Agent:**
1. Go to log analysis section
2. Upload a sample log file
3. Verify detailed analysis appears

**Test Research Agent:**
1. Ask: "What's the latest news about Mailbird?"
2. Verify it searches and provides cited information

### 3. Rate Limiting Verification

**Check Rate Limit Status:**
```powershell
curl http://localhost:8000/api/v1/rate-limits/status
```

### 4. Database Connectivity

**Test Database Connection:**
```powershell
python -c "
from app.db.connection_manager import get_connection
conn = get_connection()
print('Database connected:', conn is not None)
if conn:
    cursor = conn.cursor()
    cursor.execute('SELECT 1')
    print('Query test:', cursor.fetchone())
    conn.close()
"
```

---

## 🚨 Troubleshooting

### Common Windows Issues

**1. Python PATH Issues**
```powershell
# Add Python to PATH manually
$env:PATH += ";C:\Users\[YourUsername]\AppData\Local\Programs\Python\Python311"
```

**2. Port Already in Use**
```powershell
# Find what's using port 8000
netstat -ano | findstr :8000
# Kill the process (replace PID with actual number)
taskkill /PID [PID] /F
```

**3. Permission Denied Errors**
```powershell
# Run PowerShell as Administrator
# Or try:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**4. Redis Connection Issues**
```powershell
# Check if Redis is running
# WSL2:
wsl redis-cli ping

# Docker:
docker ps | findstr redis
docker logs redis
```

**5. Virtual Environment Issues**
```powershell
# Deactivate and recreate
deactivate
Remove-Item -Recurse -Force venv
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

**6. Node.js/npm Issues**
```powershell
# Clear npm cache
npm cache clean --force

# Delete node_modules and reinstall
Remove-Item -Recurse -Force node_modules
Remove-Item -Force package-lock.json
npm install
```

### Dependency Conflicts

**Python Dependencies:**
```powershell
# Check for conflicts
pip check

# Reinstall specific packages
pip uninstall [package_name]
pip install [package_name]
```

**Node.js Dependencies:**
```powershell
# Check for vulnerabilities
npm audit

# Fix automatically
npm audit fix
```

### API Key Issues

**Verify API Keys:**
```powershell
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('Gemini API Key:', 'SET' if os.getenv('GEMINI_API_KEY') else 'NOT SET')
print('Tavily API Key:', 'SET' if os.getenv('TAVILY_API_KEY') else 'NOT SET')
"
```

### Database Connection Issues

**Test Supabase Connection:**
```powershell
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('Supabase URL:', 'SET' if os.getenv('SUPABASE_URL') else 'NOT SET')
print('Database URL:', 'SET' if os.getenv('DATABASE_URL') else 'NOT SET')
"
```

---

## 🎯 Usage Guide

### 1. Accessing the System

**Main Interface:**
- Open browser to `http://localhost:3000`
- You'll see the MB-Sparrow welcome screen

**API Documentation:**
- Visit `http://localhost:8000/docs` for interactive API docs
- Use `http://localhost:8000/redoc` for alternative documentation

### 2. Using Different Agents

**Primary Agent (Agent Sparrow):**
- Best for general customer support questions
- Provides structured troubleshooting
- Handles email setup, account issues, and general queries

**Enhanced Log Analysis Agent:**
- Upload log files for detailed analysis
- Supports Windows, macOS, and Linux logs
- Provides ML-powered pattern discovery
- Offers predictive insights and correlations

**Research Agent:**
- Asks questions requiring web research
- Provides cited sources
- Good for latest news, updates, and external information

### 3. Uploading Files

**Log File Analysis:**
1. Click on "Upload Log File" button
2. Select log file (max 10MB)
3. Wait for analysis to complete
4. Review structured results

**FeedMe Transcript Upload:**
1. Click "FeedMe" button in header
2. Choose file upload or text input
3. Upload customer support transcripts
4. System will process and create searchable Q&A examples

### 4. Understanding Responses

**Agent Responses Include:**
- Structured troubleshooting steps
- Emotional intelligence analysis
- Tool reasoning transparency
- Progressive complexity handling
- Escalation recommendations when needed

**Log Analysis Responses Include:**
- Executive summary
- System overview
- Issue identification and categorization
- Solution recommendations
- Predictive insights
- Correlation analysis

---

## 🏗️ System Architecture

### Backend Components

```
FastAPI Backend (Port 8000)
├── Query Router (gemma-2b-it)          # Route queries to appropriate agent
├── Primary Agent (gemini-2.5-flash)   # Main customer support agent
├── Log Analysis Agent (gemini-2.5-pro) # Advanced log analysis
├── Research Agent (gemini-2.5-flash)  # Web research capabilities
└── FeedMe System                       # Transcript ingestion
```

### Frontend Components

```
Next.js Frontend (Port 3000)
├── Unified Chat Interface             # Main conversation UI
├── Agent Avatar System               # Consistent agent representation
├── Markdown Rendering               # Rich text formatting
├── Log Analysis Container           # Structured log analysis display
├── FeedMe Modal                    # Transcript upload interface
└── Rate Limiting UI                # Usage monitoring
```

### Database Schema

```
PostgreSQL + pgvector
├── mailbird_knowledge               # Knowledge base articles
├── feedme_conversations            # Uploaded transcripts
├── feedme_examples                 # Q&A examples with embeddings
├── chat_sessions                   # User conversation sessions
└── Various indexes for performance
```

### AI Models Used

- **Router**: `google/gemma-2b-it` (Fast classification)
- **Primary Agent**: `gemini-2.5-flash` (Balanced performance)
- **Log Analysis**: `gemini-2.5-pro` (Maximum capability)
- **Research Agent**: `gemini-2.5-flash/pro` (Adaptive)

### Rate Limiting (Free Tier Safe)

```
Gemini Flash: 8 requests/minute, 200 requests/day
Gemini Pro: 4 requests/minute, 80 requests/day
Circuit breaker protection
Safety margins built-in
```

---

## 🔄 Development Workflow

### Daily Development

1. **Start Backend:**
   ```powershell
   cd MB-Sparrow
   venv\Scripts\activate
   cd app
   python main.py
   ```

2. **Start Frontend:**
   ```powershell
   cd frontend
   npm run dev
   ```

3. **Check Logs:**
   - Backend logs appear in terminal
   - Frontend logs in browser console
   - Check `backend.log` and `frontend.log` files

### Testing Changes

**Run Backend Tests:**
```powershell
cd MB-Sparrow
venv\Scripts\activate
pytest tests/
```

**Run Frontend Tests:**
```powershell
cd frontend
npm test
```

### Building for Production

**Backend:**
```powershell
# Production requirements
pip install gunicorn
gunicorn app.main:app --host 0.0.0.0 --port 8000
```

**Frontend:**
```powershell
npm run build
npm start
```

---

## 📊 Performance Optimization

### System Requirements for Optimal Performance

- **CPU**: 4+ cores recommended
- **RAM**: 16GB recommended (8GB minimum)
- **SSD**: Recommended for database operations
- **Network**: Stable connection for API calls

### Configuration Tuning

**For Development:**
```env
OPTIMIZATION_THRESHOLD_LINES=500
USE_OPTIMIZED_ANALYSIS=true
ENABLE_ML_PATTERN_DISCOVERY=true
```

**For Production:**
```env
OPTIMIZATION_THRESHOLD_LINES=1000
USE_OPTIMIZED_ANALYSIS=true
ENABLE_ML_PATTERN_DISCOVERY=true
ENABLE_PREDICTIVE_ANALYSIS=true
```

---

## 🛡️ Security Considerations

### API Key Security
- Never commit `.env` files to version control
- Use environment-specific API keys
- Rotate keys periodically

### Database Security
- Use connection pooling
- Enable SSL for database connections
- Regular backup schedule

### Rate Limiting
- Built-in rate limiting protects against abuse
- Circuit breaker prevents cascading failures
- Monitoring alerts for unusual usage

---

## 📞 Support & Resources

### Getting Help

1. **Check Logs First:**
   - Backend: `backend.log`
   - Frontend: Browser console
   - System: Windows Event Viewer

2. **Common Solutions:**
   - Restart services
   - Check environment variables
   - Verify API keys
   - Test database connectivity

3. **Community Resources:**
   - Project documentation
   - GitHub issues
   - Stack Overflow tags

### Useful Commands Reference

```powershell
# Quick system check
python --version && node --version && git --version

# Restart all services
# Kill existing processes, then:
venv\Scripts\activate && cd app && python main.py
# In new terminal:
cd frontend && npm run dev

# Check service status
netstat -ano | findstr :8000  # Backend
netstat -ano | findstr :3000  # Frontend
```

---

## 🎉 You're Ready!

Your MB-Sparrow system should now be running successfully on Windows. The system provides:

✅ **Multi-Agent AI Support** with intelligent routing  
✅ **Advanced Log Analysis** with ML-powered insights  
✅ **Research Capabilities** with web search integration  
✅ **Customer Transcript Processing** via FeedMe  
✅ **Rate Limiting Protection** for API usage  
✅ **Modern UI** with Mailbird branding  
✅ **Comprehensive Error Handling** and monitoring  

Visit `http://localhost:3000` to start using your MB-Sparrow system!

---

*Last Updated: January 2025 | Version: 1.0*