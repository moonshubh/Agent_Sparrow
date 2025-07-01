# Understanding Free Tier Usage - MB-Sparrow

## What Are Rate Limits?

MB-Sparrow uses Google's Gemini AI models to provide intelligent customer support. To keep the service free for everyone, we operate within Google's free tier limits, which means there are restrictions on how many AI requests can be made per minute and per day.

## Current Free Tier Limits

### Gemini 2.5 Flash (Primary Support)
- **Per Minute**: 8 requests
- **Per Day**: 200 requests
- **Use Case**: General customer support, quick questions

### Gemini 2.5 Pro (Advanced Analysis)  
- **Per Minute**: 4 requests
- **Per Day**: 80 requests
- **Use Case**: Complex log analysis, detailed troubleshooting

## How to Monitor Your Usage

### In the Chat Interface

#### Header Status (Desktop)
Look for the "Rate Limits" card in the top-right header:
- **Green bars**: Normal usage, plenty of capacity remaining
- **Yellow bars**: Approaching limits, moderate usage
- **Red bars**: High usage, limits may be reached soon

#### Warning Alerts
When usage gets high, you'll see helpful alerts:
- **Yellow warning**: "Approaching rate limits" - at 70% usage
- **Red critical**: "Rate limits nearly exhausted" - at 85% usage

### Understanding the Display

#### What the Numbers Mean
- **RPM**: Requests per minute (resets every minute)
- **RPD**: Requests per day (resets at midnight UTC)
- **Usage percentage**: How much of the daily limit has been used

#### Example Reading
```
Flash (2.5): 6/8 RPM
- This means 6 out of 8 requests used this minute
- Progress bar shows 75% (yellow/orange color)
- 2 more requests available this minute
```

## What Happens When Limits Are Reached?

### Temporary Blocking
When you reach a rate limit, you'll see a helpful dialog explaining:
- Which model/limit was reached (Flash or Pro, per-minute or per-day)
- How long until the limit resets
- What you can do while waiting

### Reset Times
- **Per-minute limits**: Reset every 60 seconds
- **Per-day limits**: Reset at midnight UTC (8 PM EST / 5 PM PST)

### Your Options
1. **Wait for reset**: The countdown shows exactly when you can try again
2. **Try different approach**: Use simpler queries that might use the other model
3. **Come back later**: Especially helpful if daily limits are reached

## Tips for Efficient Usage

### General Guidelines
1. **Be specific**: Clear, focused questions get better answers with fewer follow-ups
2. **Combine questions**: Ask multiple related questions in one message
3. **Use simple language**: Complex queries might trigger the more limited Pro model

### Smart Usage Strategies

#### For Log Analysis
- Upload complete log files rather than snippets (more efficient analysis)
- Describe the specific issue you're seeing
- Include relevant timeframes and error symptoms

#### For General Support
- Start with specific error messages or symptoms
- Provide step-by-step descriptions of what you tried
- Include relevant system information (OS, Mailbird version, etc.)

### Peak Usage Awareness
Usage tends to be higher during:
- Business hours (9 AM - 5 PM in major time zones)
- Monday mornings and Friday afternoons
- After new Mailbird releases or updates

## Understanding the Free Tier Benefits

### Why Limits Exist
Rate limits help us:
- Keep MB-Sparrow completely free for all users
- Ensure fair access for everyone
- Maintain consistent response quality
- Stay within Google's generous free tier allowances

### Our Safety Margin
We set our limits at 80% of Google's actual limits, which means:
- **Safety buffer**: 20% cushion prevents any overage charges
- **Consistent availability**: Rare to hit hard limits
- **Predictable experience**: You know exactly what to expect

## Getting Help When Limited

### Immediate Options
1. **Check the countdown**: See exactly when limits reset
2. **Review your question**: Can it be simplified or combined with others?
3. **Use search**: Check if similar questions have been answered recently

### Alternative Resources
While waiting for limits to reset:
- **Mailbird Help Center**: Comprehensive self-service documentation
- **Community Forums**: User discussions and solutions
- **Knowledge Base**: Searchable database of common solutions

### Contact Support
For urgent issues when rate limited:
- Use the traditional support form (non-AI assistance)
- Email support directly for critical problems
- Check status page for known issues

## Advanced Users: Admin Dashboard

If you have administrative access, the admin dashboard (`/admin/rate-limits`) provides:

### Detailed Metrics
- Real-time usage graphs
- Historical usage patterns
- Circuit breaker status
- System health monitoring

### Export Capabilities
- Download usage reports
- Analyze usage patterns
- Plan for peak usage periods

### Emergency Controls
- Rate limit reset capabilities (emergency use only)
- System configuration visibility
- Health check results

## Frequently Asked Questions

### "Why can't I use unlimited AI?"
Google's Gemini models have generous but finite free tier limits. Operating within these limits keeps MB-Sparrow completely free for all users.

### "Can I pay to remove limits?"
Currently, MB-Sparrow operates as a free service. We're exploring paid tiers with higher limits for the future.

### "What if I'm always hitting limits?"
Contact our team! We can analyze your usage patterns and suggest optimization strategies or discuss priority access options.

### "Are limits per user or system-wide?"
Limits are currently system-wide to keep the service simple and free. All users share the daily quotas fairly.

### "Why do limits seem to change?"
Limits are fixed, but your perception might change based on:
- Other users' concurrent usage
- Different models being selected automatically
- Time of day affecting overall system usage

## Troubleshooting

### "Status not updating"
1. Refresh your browser page
2. Check your internet connection
3. Clear browser cache if issues persist

### "Getting limits when bars show green"
1. There might be a delay in status updates (up to 15 seconds)
2. Other users might have consumed remaining quota
3. Try refreshing to get current status

### "Warning won't dismiss"
1. Click the X button in the top-right of the warning
2. The warning may reappear if usage remains high
3. This is normal behavior to keep you informed

## Providing Feedback

We're constantly improving the rate limiting experience:

### What's Working Well
- Is the status display helpful?
- Are warnings appearing at the right time?
- Is the guidance clear when limits are reached?

### What Could Be Better
- Are messages confusing or unclear?
- Do you need different information displayed?
- Would you like additional features or controls?

### How to Share Feedback
- Use the feedback form in the app
- Email our product team
- Join our user research program
- Participate in community discussions

---

**Remember**: Rate limits exist to keep MB-Sparrow free and available for everyone. The system is designed to be transparent and helpful, guiding you to the best possible experience within our free tier constraints.

**Questions?** Contact our support team - we're here to help you get the most out of MB-Sparrow!