"""
Rate limiter for Google Gemini embedding API

Implements rate limiting for the free tier of gemini-embedding-001:
- 100 RPM (requests per minute)
- 30,000 TPM (tokens per minute)  
- 1,000 RPD (requests per day)
"""

import asyncio
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class EmbeddingRateLimiter:
    """Rate limiter for Gemini embeddings with free tier limits"""
    
    def __init__(
        self,
        max_requests_per_minute: int = 90,  # 90% of 100 RPM for safety
        max_tokens_per_minute: int = 27000,  # 90% of 30k TPM for safety
        max_requests_per_day: int = 900,  # 90% of 1k RPD for safety
    ):
        self.max_rpm = max_requests_per_minute
        self.max_tpm = max_tokens_per_minute
        self.max_rpd = max_requests_per_day
        
        # Request tracking
        self.minute_requests: list[float] = []
        self.minute_tokens: list[tuple[float, int]] = []
        self.day_requests: list[float] = []
        
        # Lock for thread safety
        self.lock = asyncio.Lock()
        
    async def check_limits(self, token_count: int) -> bool:
        """Check if request would exceed rate limits"""
        async with self.lock:
            now = time.time()
            
            # Clean old entries
            self._clean_old_entries(now)
            
            # Check daily limit
            if len(self.day_requests) >= self.max_rpd:
                logger.warning("Daily request limit reached")
                return False
                
            # Check minute request limit
            if len(self.minute_requests) >= self.max_rpm:
                logger.warning("Minute request limit reached")
                return False
                
            # Check minute token limit
            current_minute_tokens = sum(tokens for _, tokens in self.minute_tokens)
            if current_minute_tokens + token_count > self.max_tpm:
                logger.warning(f"Minute token limit would be exceeded: {current_minute_tokens} + {token_count} > {self.max_tpm}")
                return False
                
            return True
            
    async def record_request(self, token_count: int):
        """Record a successful request"""
        async with self.lock:
            now = time.time()
            self.minute_requests.append(now)
            self.minute_tokens.append((now, token_count))
            self.day_requests.append(now)
            
    def _clean_old_entries(self, now: float):
        """Remove entries older than time windows"""
        # Clean minute-based entries (older than 60 seconds)
        minute_cutoff = now - 60
        self.minute_requests = [t for t in self.minute_requests if t > minute_cutoff]
        self.minute_tokens = [(t, tokens) for t, tokens in self.minute_tokens if t > minute_cutoff]
        
        # Clean day-based entries (older than 24 hours)
        day_cutoff = now - (24 * 60 * 60)
        self.day_requests = [t for t in self.day_requests if t > day_cutoff]
        
    async def wait_if_needed(self, token_count: int) -> float:
        """Calculate wait time if rate limit would be exceeded"""
        async with self.lock:
            now = time.time()
            self._clean_old_entries(now)
            
            wait_times = []
            
            # Check daily limit
            if len(self.day_requests) >= self.max_rpd:
                oldest_day_request = min(self.day_requests)
                wait_time = (oldest_day_request + 24 * 60 * 60) - now
                wait_times.append(wait_time)
                
            # Check minute request limit
            if len(self.minute_requests) >= self.max_rpm:
                oldest_minute_request = min(self.minute_requests)
                wait_time = (oldest_minute_request + 60) - now
                wait_times.append(wait_time)
                
            # Check minute token limit
            current_minute_tokens = sum(tokens for _, tokens in self.minute_tokens)
            if current_minute_tokens + token_count > self.max_tpm:
                # Find when enough tokens will expire
                tokens_to_free = (current_minute_tokens + token_count) - self.max_tpm
                freed_tokens = 0
                for t, tokens in sorted(self.minute_tokens):
                    freed_tokens += tokens
                    if freed_tokens >= tokens_to_free:
                        wait_time = (t + 60) - now
                        wait_times.append(wait_time)
                        break
                        
            return max(wait_times) if wait_times else 0
            
    def get_stats(self) -> Dict[str, Any]:
        """Get current rate limiter statistics"""
        now = time.time()
        self._clean_old_entries(now)
        
        current_minute_tokens = sum(tokens for _, tokens in self.minute_tokens)
        
        return {
            "requests_per_minute": len(self.minute_requests),
            "tokens_per_minute": current_minute_tokens,
            "requests_today": len(self.day_requests),
            "rpm_limit": self.max_rpm,
            "tpm_limit": self.max_tpm,
            "rpd_limit": self.max_rpd,
            "rpm_remaining": self.max_rpm - len(self.minute_requests),
            "tpm_remaining": self.max_tpm - current_minute_tokens,
            "rpd_remaining": self.max_rpd - len(self.day_requests),
        }


# Global instance for the application
embedding_limiter = EmbeddingRateLimiter()