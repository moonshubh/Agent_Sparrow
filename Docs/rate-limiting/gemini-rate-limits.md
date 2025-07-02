# Google Gemini Free Tier Rate Limits (2025)

## Research Findings

Based on the official Google AI Developer documentation, here are the exact rate limits for Gemini models in the free tier:

### Gemini 2.5 Flash
- **Requests per Minute (RPM)**: 10
- **Tokens per Minute (TPM)**: 250,000
- **Requests per Day (RPD)**: 250

### Gemini 2.5 Pro
- **Requests per Minute (RPM)**: 5
- **Tokens per Minute (TPM)**: 250,000
- **Requests per Day (RPD)**: 100

## Important Notes

1. **Rate limits are applied per project, not per API key**
2. **Token limits**: While token per minute limits are generous (250K), the request limits are restrictive
3. **Error handling**: Exceeding limits results in `429 RESOURCE_EXHAUSTED` errors
4. **Cost**: Input and output tokens within rate limits are completely free

## Critical Risk Analysis

For MB-Sparrow's usage patterns:

### Primary Agent (gemini-2.5-flash):
- **Risk Level**: MEDIUM
- **Usage**: Customer support queries
- **Current limit**: 10 RPM / 250 RPD
- **Risk**: Could exceed daily limit with moderate usage

### Log Analysis Agent (gemini-2.5-pro):
- **Risk Level**: HIGH
- **Usage**: Complex log processing
- **Current limit**: 5 RPM / 100 RPD  
- **Risk**: Very likely to exceed limits in production

## Recommended Safety Margins

To ensure zero overage charges:
- **Flash safety limit**: 8 RPM / 200 RPD (80% of limits)
- **Pro safety limit**: 4 RPM / 80 RPD (80% of limits)
- **Fallback strategies**: Queue requests, use caching, graceful degradation

## Sources

- [Google AI Developer Rate Limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing)

---
**Last Updated**: 2025-07-01
**Next Review**: When Google updates free tier limits