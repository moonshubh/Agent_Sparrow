# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2025-06-26

### Fixed
- **Fix hydration mismatch due to browser extensions**: Added `suppressHydrationWarning` to body element and Grammarly disable script to prevent React hydration warnings caused by browser extension attribute injection
- **Restore FeedMe API connectivity**: Fixed API base URL configuration to use deterministic paths without `typeof window` checks, ensuring proper operation with Next.js rewrites
- **Enhanced error handling**: Added `ApiUnreachableError` class with friendly error messages and exponential backoff retry logic for improved user experience during network failures
- **Deterministic SSR theme rendering**: Synchronized ThemeProvider defaultTheme with server-side cookie values to eliminate hydration mismatches
- **Removed typeof window dependencies**: Eliminated all `typeof window` checks in components to ensure consistent SSR/CSR behavior

### Security
- **Database function security**: Fixed Supabase search_path security warnings by adding immutable `SET search_path = ''` to all database functions with `SECURITY DEFINER`

### Changed
- **Environment configuration**: Updated `.env.local` to use relative API paths (`/api/v1`) instead of absolute URLs for proper Next.js rewrite operation
- **Window dimension handling**: Replaced `typeof window` checks with proper client-side state management for responsive components

### Added
- **Comprehensive error logging**: Enhanced FeedMe API client with detailed request/response logging for better debugging
- **Regression tests**: Added test coverage for hydration fixes and API configuration to prevent future regressions

---

## Previous Releases

### [2.0.0] - FeedMe v2.0 Enhanced Log Analysis Agent v3.0
- World-class production-grade log analysis system implementation
- 5-phase analysis pipeline with ML pattern discovery
- Cross-platform support (Windows/macOS/Linux) 
- Multi-language analysis (10 languages)
- Predictive analysis and correlation detection
- Enhanced UI with tabbed interface and progressive disclosure

### [1.0.0] - Initial Release
- Multi-agent AI system for Mailbird customer support
- Agent Sparrow v8.0 with structured troubleshooting
- Query routing with confidence-based agent selection
- Next.js 15 frontend with shadcn/ui components
- FastAPI backend with LangGraph agent orchestration