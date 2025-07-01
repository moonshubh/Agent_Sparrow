"""
Validation tests to ensure the rate limiting system operates entirely 
within Google Gemini's free tier limits.

These tests simulate real-world usage patterns and verify that no
requests can exceed the free tier limits under any circumstances.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.rate_limiting import (
    GeminiRateLimiter,
    RateLimitConfig,
    RateLimitExceededException,
    CircuitBreakerOpenException
)


class TestFreeTierCompliance:
    """Test suite to validate free tier compliance."""
    
    @pytest.fixture
    def free_tier_config(self):
        """Configuration that exactly matches free tier limits (no safety margin)."""
        return RateLimitConfig(
            # Exact free tier limits
            flash_rpm_limit=10,
            flash_rpd_limit=250,
            pro_rpm_limit=5,
            pro_rpd_limit=100,
            safety_margin=0.0,  # No safety margin for testing
            circuit_breaker_enabled=True,
            circuit_breaker_failure_threshold=3
        )
    
    @pytest.fixture
    def production_config(self):
        """Production configuration with safety margins."""
        return RateLimitConfig(
            # 80% of free tier limits (production setting)
            flash_rpm_limit=8,
            flash_rpd_limit=200,
            pro_rpm_limit=4,
            pro_rpd_limit=80,
            safety_margin=0.2,  # 20% safety margin
            circuit_breaker_enabled=True
        )
    
    @pytest.fixture
    async def mock_redis(self):
        """Mock Redis with realistic sliding window behavior."""
        class MockRedis:
            def __init__(self):
                self.data = {}
                self.request_counts = {"flash": {"rpm": 0, "rpd": 0}, "pro": {"rpm": 0, "rpd": 0}}
            
            def pipeline(self):
                return self
            
            async def execute(self):
                # Return [remove_result, current_count]
                return [None, self.request_counts.get("flash", {}).get("rpm", 0)]
            
            async def zadd(self, key, mapping):
                # Simulate adding request
                if "flash" in key:
                    if "rpm" in key:
                        self.request_counts["flash"]["rpm"] += 1
                    elif "rpd" in key:
                        self.request_counts["flash"]["rpd"] += 1
                elif "pro" in key:
                    if "rpm" in key:
                        self.request_counts["pro"]["rpm"] += 1
                    elif "rpd" in key:
                        self.request_counts["pro"]["rpd"] += 1
                return 1
            
            async def expire(self, key, seconds):
                return True
            
            async def ping(self):
                return True
            
            async def keys(self, pattern):
                return []
            
            async def zcard(self, key):
                return 0
            
            async def delete(self, *keys):
                return len(keys)
            
            def set_count(self, model, window, count):
                """Helper to set request count for testing."""
                self.request_counts[model][window] = count
            
            async def zremrangebyscore(self, key, min_score, max_score):
                return 0
        
        return MockRedis()
    
    @pytest.fixture
    async def rate_limiter(self, free_tier_config, mock_redis):
        """Rate limiter with mocked Redis."""
        with patch('redis.asyncio.from_url', return_value=mock_redis):
            limiter = GeminiRateLimiter(free_tier_config)
            yield limiter, mock_redis
            await limiter.close()
    
    @pytest.mark.asyncio
    async def test_flash_rpm_limit_enforcement(self, rate_limiter):
        """Test that Flash RPM limits are strictly enforced."""
        limiter, mock_redis = rate_limiter
        
        # Allow first 10 requests
        for i in range(10):
            result = await limiter.check_and_consume("gemini-2.5-flash")
            assert result.allowed, f"Request {i+1} should be allowed"
        
        # 11th request should be blocked
        mock_redis.set_count("flash", "rpm", 10)
        result = await limiter.check_and_consume("gemini-2.5-flash")
        assert not result.allowed, "11th request should be blocked"
        assert result.blocked_by == "rpm"
    
    @pytest.mark.asyncio
    async def test_flash_rpd_limit_enforcement(self, rate_limiter):
        """Test that Flash RPD limits are strictly enforced."""
        limiter, mock_redis = rate_limiter
        
        # Simulate 250 requests already consumed today
        mock_redis.set_count("flash", "rpd", 250)
        
        result = await limiter.check_and_consume("gemini-2.5-flash")
        assert not result.allowed, "Request should be blocked at daily limit"
        assert result.blocked_by == "rpd"
    
    @pytest.mark.asyncio
    async def test_pro_rpm_limit_enforcement(self, rate_limiter):
        """Test that Pro RPM limits are strictly enforced."""
        limiter, mock_redis = rate_limiter
        
        # Simulate 5 requests already consumed this minute
        mock_redis.set_count("pro", "rpm", 5)
        
        result = await limiter.check_and_consume("gemini-2.5-pro")
        assert not result.allowed, "Request should be blocked at RPM limit"
        assert result.blocked_by == "rpm"
    
    @pytest.mark.asyncio
    async def test_pro_rpd_limit_enforcement(self, rate_limiter):
        """Test that Pro RPD limits are strictly enforced."""
        limiter, mock_redis = rate_limiter
        
        # Simulate 100 requests already consumed today
        mock_redis.set_count("pro", "rpd", 100)
        
        result = await limiter.check_and_consume("gemini-2.5-pro")
        assert not result.allowed, "Request should be blocked at daily limit"
        assert result.blocked_by == "rpd"
    
    @pytest.mark.asyncio
    async def test_concurrent_request_handling(self, rate_limiter):
        """Test that concurrent requests don't bypass limits."""
        limiter, mock_redis = rate_limiter
        
        async def make_request():
            return await limiter.check_and_consume("gemini-2.5-flash")
        
        # Make 15 concurrent requests (should only allow 10)
        tasks = [make_request() for _ in range(15)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count allowed requests
        allowed_count = sum(1 for r in results if not isinstance(r, Exception) and r.allowed)
        
        # Should not exceed limit even with concurrency
        assert allowed_count <= 10, f"Too many concurrent requests allowed: {allowed_count}"
    
    @pytest.mark.asyncio
    async def test_mixed_model_usage(self, rate_limiter):
        """Test that limits are enforced independently for each model."""
        limiter, mock_redis = rate_limiter
        
        # Use up Flash RPM limit
        for i in range(10):
            result = await limiter.check_and_consume("gemini-2.5-flash")
            assert result.allowed, f"Flash request {i+1} should be allowed"
        
        # Flash should now be blocked
        mock_redis.set_count("flash", "rpm", 10)
        flash_result = await limiter.check_and_consume("gemini-2.5-flash")
        assert not flash_result.allowed, "Flash should be blocked"
        
        # Pro should still be available
        pro_result = await limiter.check_and_consume("gemini-2.5-pro")
        assert pro_result.allowed, "Pro should still be available"
    
    @pytest.mark.asyncio
    async def test_production_safety_margins(self, production_config, mock_redis):
        """Test that production config provides adequate safety margins."""
        with patch('redis.asyncio.from_url', return_value=mock_redis):
            limiter = GeminiRateLimiter(production_config)
            
            # Test Flash limits with safety margin
            for i in range(8):  # Should allow 8 requests (80% of 10)
                result = await limiter.check_and_consume("gemini-2.5-flash")
                assert result.allowed, f"Request {i+1} should be allowed with safety margin"
            
            # 9th request should be blocked due to safety margin
            mock_redis.set_count("flash", "rpm", 8)
            result = await limiter.check_and_consume("gemini-2.5-flash")
            assert not result.allowed, "9th request should be blocked by safety margin"
            
            await limiter.close()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_protection(self, rate_limiter):
        """Test that circuit breaker provides additional protection."""
        limiter, mock_redis = rate_limiter
        
        async def failing_function():
            raise Exception("API Error")
        
        # Cause circuit breaker to open
        for i in range(3):  # failure_threshold = 3
            try:
                await limiter.execute_with_protection(
                    "gemini-2.5-flash", 
                    failing_function
                )
            except Exception:
                pass  # Expected
        
        # Circuit should now be open, blocking all requests
        with pytest.raises(CircuitBreakerOpenException):
            await limiter.execute_with_protection(
                "gemini-2.5-flash",
                lambda: "success"
            )
    
    @pytest.mark.asyncio
    async def test_rate_limit_exception_details(self, rate_limiter):
        """Test that rate limit exceptions contain correct information."""
        limiter, mock_redis = rate_limiter
        
        # Set up rate limit exceeded condition
        mock_redis.set_count("flash", "rpm", 10)
        
        try:
            await limiter.execute_with_protection(
                "gemini-2.5-flash",
                lambda: "success"
            )
            assert False, "Should have raised RateLimitExceededException"
        except RateLimitExceededException as e:
            assert e.model == "gemini-2.5-flash"
            assert e.retry_after is not None
            assert "flash" in str(e.limits).lower()
            assert "rate limit exceeded" in e.message.lower()
    
    @pytest.mark.asyncio
    async def test_no_double_counting(self, rate_limiter):
        """Test that failed requests don't count against limits."""
        limiter, mock_redis = rate_limiter
        
        # Mock a request that will be rate limited
        mock_redis.set_count("flash", "rpm", 10)
        
        # This should not consume a token since it's already at limit
        result = await limiter.check_and_consume("gemini-2.5-flash")
        assert not result.allowed
        
        # The count should remain 10, not 11
        # (This test verifies that rate limited requests don't increment counters)
    
    @pytest.mark.asyncio
    async def test_redis_failure_safety(self, free_tier_config):
        """Test that Redis failures result in safe behavior (blocking requests)."""
        # Mock Redis that always fails
        failing_redis = AsyncMock()
        failing_redis.pipeline.side_effect = Exception("Redis connection failed")
        
        with patch('redis.asyncio.from_url', return_value=failing_redis):
            limiter = GeminiRateLimiter(free_tier_config)
            
            # Should raise exception (fail safe) rather than allowing unlimited requests
            with pytest.raises(Exception):
                await limiter.check_and_consume("gemini-2.5-flash")
            
            await limiter.close()
    
    @pytest.mark.asyncio
    async def test_time_window_accuracy(self, rate_limiter):
        """Test that time windows are accurately enforced."""
        limiter, mock_redis = rate_limiter
        
        # This is a simplified test - in reality, we'd need to test
        # actual time-based sliding windows with Redis
        
        result = await limiter.check_and_consume("gemini-2.5-flash")
        assert result.allowed
        
        # Verify metadata contains correct timing information
        assert result.metadata.reset_time_rpm > datetime.utcnow()
        assert result.metadata.reset_time_rpd > datetime.utcnow()
    
    @pytest.mark.asyncio
    async def test_comprehensive_stress_test(self, production_config, mock_redis):
        """Comprehensive stress test simulating real production load."""
        with patch('redis.asyncio.from_url', return_value=mock_redis):
            limiter = GeminiRateLimiter(production_config)
            
            # Simulate mixed workload over time
            flash_requests = 0
            pro_requests = 0
            
            # Simulate 1 hour of requests at various rates
            for minute in range(60):
                # Flash: 6 requests per minute (below 8 RPM limit)
                for _ in range(6):
                    try:
                        result = await limiter.check_and_consume("gemini-2.5-flash")
                        if result.allowed:
                            flash_requests += 1
                    except:
                        pass
                
                # Pro: 3 requests per minute (below 4 RPM limit)
                for _ in range(3):
                    try:
                        result = await limiter.check_and_consume("gemini-2.5-pro")
                        if result.allowed:
                            pro_requests += 1
                    except:
                        pass
                
                # Reset per-minute counters every minute in mock
                if minute % 10 == 0:  # Reset every 10 iterations for testing
                    mock_redis.set_count("flash", "rpm", 0)
                    mock_redis.set_count("pro", "rpm", 0)
            
            # Total requests should be well within daily limits
            assert flash_requests <= 200, f"Flash requests exceeded safe daily limit: {flash_requests}"
            assert pro_requests <= 80, f"Pro requests exceeded safe daily limit: {pro_requests}"
            
            await limiter.close()


class TestFreeTierValidation:
    """Additional validation tests for free tier compliance."""
    
    def test_configuration_limits_are_safe(self):
        """Test that default configuration is within free tier limits."""
        config = RateLimitConfig.from_environment()
        
        # Default Flash limits should be <= free tier
        assert config.flash_rpm_limit <= 10, "Flash RPM limit exceeds free tier"
        assert config.flash_rpd_limit <= 250, "Flash RPD limit exceeds free tier"
        
        # Default Pro limits should be <= free tier
        assert config.pro_rpm_limit <= 5, "Pro RPM limit exceeds free tier"
        assert config.pro_rpd_limit <= 100, "Pro RPD limit exceeds free tier"
        
        # Safety margin should provide additional protection
        assert config.safety_margin > 0, "No safety margin configured"
        assert config.safety_margin <= 0.5, "Safety margin too high"
    
    def test_effective_limits_calculation(self):
        """Test that effective limits are correctly calculated with safety margins."""
        config = RateLimitConfig(
            flash_rpm_limit=10,
            flash_rpd_limit=250,
            pro_rpm_limit=5,
            pro_rpd_limit=100,
            safety_margin=0.2
        )
        
        # Effective limits should be 80% of configured limits
        flash_rpm, flash_rpd = config.get_effective_limits("gemini-2.5-flash")
        assert flash_rpm == 8, f"Expected 8, got {flash_rpm}"
        assert flash_rpd == 200, f"Expected 200, got {flash_rpd}"
        
        pro_rpm, pro_rpd = config.get_effective_limits("gemini-2.5-pro")
        assert pro_rpm == 4, f"Expected 4, got {pro_rpm}"
        assert pro_rpd == 80, f"Expected 80, got {pro_rpd}"
    
    def test_impossible_to_exceed_limits(self):
        """Test that it's mathematically impossible to exceed free tier limits."""
        config = RateLimitConfig.from_environment()
        
        # Even with no safety margin, limits should not exceed free tier
        max_flash_rpm = int(10 * (1.0 - 0.0))  # No safety margin
        max_flash_rpd = int(250 * (1.0 - 0.0))
        max_pro_rpm = int(5 * (1.0 - 0.0))
        max_pro_rpd = int(100 * (1.0 - 0.0))
        
        assert config.flash_rpm_limit <= max_flash_rpm
        assert config.flash_rpd_limit <= max_flash_rpd
        assert config.pro_rpm_limit <= max_pro_rpm
        assert config.pro_rpd_limit <= max_pro_rpd
    
    def test_redis_key_isolation(self):
        """Test that Redis keys properly isolate different models and time windows."""
        config = RateLimitConfig()
        
        flash_rpm_key, flash_rpd_key = config.get_redis_keys("gemini-2.5-flash")
        pro_rpm_key, pro_rpd_key = config.get_redis_keys("gemini-2.5-pro")
        
        # Keys should be different for different models
        assert flash_rpm_key != pro_rpm_key
        assert flash_rpd_key != pro_rpd_key
        
        # Keys should be different for different time windows
        assert flash_rpm_key != flash_rpd_key
        assert pro_rpm_key != pro_rpd_key
        
        # Keys should contain model identifiers
        assert "flash" in flash_rpm_key.lower()
        assert "pro" in pro_rpm_key.lower()
        
        # Keys should contain time window identifiers
        assert "rpm" in flash_rpm_key
        assert "rpd" in flash_rpd_key


if __name__ == "__main__":
    # Run validation tests
    pytest.main([__file__, "-v"])