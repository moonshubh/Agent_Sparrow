# Rate Limiting Production Guide

## Overview

This guide covers the production operation of the MB-Sparrow rate limiting system, which ensures zero Google Gemini free tier overage while providing optimal user experience.

## System Architecture

### Backend Components
- **GeminiRateLimiter**: Core rate limiting engine
- **Redis Storage**: Token bucket and usage tracking
- **Circuit Breakers**: Automatic failure protection
- **API Endpoints**: RESTful monitoring and control interfaces

### Frontend Components
- **RateLimitStatus**: Header status display
- **RateLimitWarning**: Intelligent alert system
- **RateLimitDialog**: Limit reached user interface
- **RateLimitMetrics**: Administrative dashboard
- **useRateLimiting**: State management hook

## Monitoring

### Real-time Dashboards

#### User Interface Monitoring
- **Header Status**: Always visible, updates every 15 seconds
- **Warning System**: Alerts at 70% and 85% utilization
- **Model Status**: Individual Flash/Pro model monitoring

#### Admin Dashboard (`/admin/rate-limits`)
- **Overview Tab**: System health and key metrics
- **Metrics Tab**: Detailed charts and utilization graphs
- **Controls Tab**: Emergency reset capabilities
- **Config Tab**: Current configuration display

### Key Metrics to Monitor

```bash
# Flash Model Metrics
gemini_flash_rpm_used / gemini_flash_rpm_limit     # Should stay < 0.8
gemini_flash_rpd_used / gemini_flash_rpd_limit     # Should stay < 0.8

# Pro Model Metrics  
gemini_pro_rpm_used / gemini_pro_rpm_limit         # Should stay < 0.8
gemini_pro_rpd_used / gemini_pro_rpd_limit         # Should stay < 0.8

# System Health
uptime_percentage                                    # Should be > 99%
circuit_breaker_failures                           # Should be 0
```

### Alert Thresholds

| Level | Threshold | Action Required |
|-------|-----------|----------------|
| **Normal** | 0-70% | Monitor only |
| **Warning** | 70-85% | Increased monitoring |
| **Critical** | 85-95% | Consider usage reduction |
| **Emergency** | 95%+ | Automatic circuit breaker |

## Operational Procedures

### Daily Operations

#### Morning Checklist
1. Check admin dashboard for overnight usage
2. Verify all circuit breakers are closed
3. Review any warning alerts from previous day
4. Confirm auto-refresh is working on status displays

#### Monitoring Throughout Day
1. Watch for warning alerts in chat interface
2. Monitor admin dashboard during peak usage hours
3. Check for any API errors in frontend components
4. Verify user experience remains smooth

### Weekly Operations

#### Usage Analysis
1. Export metrics from admin dashboard
2. Analyze usage patterns and trends
3. Document any unusual spikes or patterns
4. Plan for any needed configuration adjustments

#### System Health Review
1. Review circuit breaker activation history
2. Check API response times and error rates
3. Verify frontend component performance
4. Update documentation if needed

### Emergency Procedures

#### Rate Limit Exceeded Emergency
1. **Immediate**: Check admin dashboard for current status
2. **Assess**: Determine which model/limit was exceeded
3. **Communicate**: Notify users via appropriate channels
4. **Action**: Use admin reset controls if absolutely necessary
5. **Follow-up**: Document incident and review usage patterns

#### System Failure Emergency
1. **Check**: Backend rate limiting service status
2. **Verify**: Redis connectivity and health
3. **Monitor**: Frontend graceful degradation
4. **Escalate**: Contact backend team if service down
5. **Communicate**: Keep users informed of any issues

## Configuration Management

### Production Configuration

#### Backend Limits (80% of Google Free Tier)
```bash
# Gemini 2.5 Flash (Google: 10 RPM, 250 RPD)
GEMINI_FLASH_RPM_LIMIT=8
GEMINI_FLASH_RPD_LIMIT=200

# Gemini 2.5 Pro (Google: 5 RPM, 100 RPD)  
GEMINI_PRO_RPM_LIMIT=4
GEMINI_PRO_RPD_LIMIT=80

# Safety Configuration
RATE_LIMIT_SAFETY_MARGIN=0.2
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
```

#### Frontend Configuration
```typescript
// Component refresh intervals
HEADER_STATUS_INTERVAL=15000        // 15 seconds
WARNING_CHECK_INTERVAL=10000        // 10 seconds  
ADMIN_DASHBOARD_INTERVAL=30000      // 30 seconds

// Alert thresholds
WARNING_THRESHOLD=0.7               // 70%
CRITICAL_THRESHOLD=0.85             // 85%
```

### Configuration Changes

#### Process for Limit Adjustments
1. **Analysis**: Review usage data and justification
2. **Testing**: Test changes in development environment
3. **Approval**: Get stakeholder approval for changes
4. **Deployment**: Apply backend configuration changes
5. **Monitoring**: Verify frontend updates automatically
6. **Documentation**: Update this guide with new values

## User Experience Guidelines

### Normal Operation
- Users see unobtrusive status in header
- Chat interface works without interruption
- No warnings or alerts displayed

### Warning State (70-85% usage)
- Yellow warning alert appears in chat area
- Users can dismiss alert if desired
- Status indicator shows warning state
- Provide guidance on usage optimization

### Critical State (85%+ usage)
- Red critical alert with stronger messaging
- Recommend reducing usage or waiting
- Clear countdown to reset times
- Educational content about free tier limits

### Rate Limited State
- Modal dialog explains situation clearly
- Countdown timer to reset
- Options to retry or cancel current request
- Educational content about why limits exist

## API Integration

### Health Check Endpoints

```bash
# System health
GET /api/v1/rate-limits/health
# Expected: {"overall": "healthy"}

# Current status  
GET /api/v1/rate-limits/status
# Expected: {"status": "healthy", "details": {...}}

# Usage metrics
GET /api/v1/rate-limits/metrics
# Expected: Prometheus-style metrics
```

### Frontend Error Handling

#### API Failure Scenarios
1. **Network Error**: Display cached status, show connection warning
2. **Server Error**: Graceful degradation, retry with backoff
3. **Invalid Response**: Log error, use fallback data
4. **Timeout**: Cancel request, use last known good data

#### User Impact Mitigation
- Frontend continues working even if rate limit API is down
- Users can still chat (rate limiting enforced by backend)
- Status shows "checking..." instead of errors
- Admin controls disabled during API failures

## Troubleshooting

### Common Issues

#### "Rate limit status not updating"
1. Check browser network tab for API errors
2. Verify backend rate limit service is running
3. Check Redis connectivity
4. Restart frontend auto-refresh timers

#### "False warnings appearing"
1. Check actual API response vs displayed data
2. Verify threshold calculations in components
3. Check for clock synchronization issues
4. Review recent configuration changes

#### "Admin dashboard not loading"
1. Verify admin route accessibility
2. Check authentication/authorization
3. Verify API endpoint availability
4. Check browser console for JavaScript errors

### Debug Information

#### Frontend Debug Mode
```javascript
// Enable debug logging in browser console
localStorage.setItem('rateLimitDebug', 'true')
// Then refresh page to see detailed logs
```

#### API Response Validation
```bash
# Check API directly
curl -X GET "http://localhost:8000/api/v1/rate-limits/status" \
  -H "Content-Type: application/json"
```

### Performance Issues

#### Slow Status Updates
1. Check API response times
2. Verify Redis performance
3. Consider reducing refresh intervals
4. Check for memory leaks in components

#### High CPU Usage
1. Monitor component re-render frequency  
2. Check for infinite refresh loops
3. Verify proper cleanup of intervals
4. Consider optimizing chart rendering

## Security Considerations

### Access Controls
- Admin dashboard requires proper authentication
- Reset operations are logged and audited
- API endpoints respect authentication tokens
- No sensitive data exposed in frontend

### Rate Limit Reset Security
- Only authorized personnel can reset limits
- All reset operations are logged with user info
- Confirmation dialogs prevent accidental resets
- Emergency use only in production

### Data Privacy
- No personal user data in rate limiting system
- Anonymous usage metrics only
- No tracking across user sessions
- Compliance with privacy regulations

## Backup and Recovery

### Data Backup
- Redis snapshots for usage data
- Configuration backup in version control
- API logs for usage analysis
- Frontend logs for error tracking

### Recovery Procedures

#### Redis Data Loss
1. Rate limits will reset to zero (safe default)
2. System will continue operating normally
3. Usage tracking restarts from clean slate
4. No user impact beyond reset counters

#### Configuration Loss
1. Restore from version control backup
2. Verify limits are properly applied
3. Test frontend components
4. Monitor for proper operation

## Maintenance Windows

### Scheduled Maintenance
- Coordinate with backend team for Redis updates
- Test frontend components after backend changes
- Verify all API endpoints after deployments
- Update documentation as needed

### Maintenance Checklist
1. Notify stakeholders of maintenance window
2. Deploy changes during low-usage periods
3. Test rate limiting after deployments
4. Monitor for issues during maintenance
5. Verify normal operation post-maintenance

## Support Contacts

### Escalation Matrix
- **Level 1**: Frontend issues, user experience problems
- **Level 2**: API integration issues, configuration problems  
- **Level 3**: Backend service issues, Redis problems
- **Level 4**: Google API quota issues, architectural problems

### Contact Information
- **Frontend Team**: For UI/UX and component issues
- **Backend Team**: For API and rate limiting service issues
- **DevOps Team**: For deployment and infrastructure issues
- **Product Team**: For business impact and user communication

---

**Document Version**: 1.0  
**Last Updated**: July 1, 2025  
**Next Review**: August 1, 2025