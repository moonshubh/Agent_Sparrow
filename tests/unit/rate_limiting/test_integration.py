"""
Integration tests for the complete rate limiting system.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from app.core.rate_limiting import (
    GeminiRateLimiter,
    RateLimitConfig,
    RateLimitExceededException,
    CircuitBreakerOpenException
)


class TestRateLimitingIntegration:
    """Integration tests for the complete rate limiting system."""
    
    @pytest.fixture
    async def mock_redis(self):
        """Mock Redis client for testing."""
        mock_redis = AsyncMock()
        mock_redis.pipeline.return_value = mock_redis
        mock_redis.execute.return_value = [None, 0]  # [remove_result, count]
        mock_redis.zadd.return_value = 1
        mock_redis.expire.return_value = True
        mock_redis.ping.return_value = True
        mock_redis.keys.return_value = []
        mock_redis.zcard.return_value = 0
        mock_redis.delete.return_value = 1
        return mock_redis
    
    @pytest.fixture
    def test_config(self):
        """Test configuration with low limits."""
        return RateLimitConfig(
            flash_rpm_limit=2,
            flash_rpd_limit=10,
            pro_rpm_limit=1,
            pro_rpd_limit=5,
            circuit_breaker_failure_threshold=2,
            circuit_breaker_timeout_seconds=5,
            safety_margin=0.0  # No safety margin for testing
        )
    
    @pytest.fixture
    async def rate_limiter(self, mock_redis, test_config):
        """Create rate limiter with mocked Redis."""
        with patch('redis.asyncio.from_url', return_value=mock_redis):
            limiter = GeminiRateLimiter(test_config)
            yield limiter
            await limiter.close()
    
    @pytest.mark.asyncio
    async def test_flash_model_rate_limiting(self, rate_limiter, mock_redis):
        """Test rate limiting for Flash model."""
        # First request should be allowed
        result1 = await rate_limiter.check_and_consume("gemini-2.5-flash")
        assert result1.allowed is True
        assert result1.metadata.model == "gemini-2.5-flash"
        
        # Verify Redis was called
        mock_redis.pipeline.assert_called()
        mock_redis.zadd.assert_called()
    
    @pytest.mark.asyncio 
    async def test_pro_model_rate_limiting(self, rate_limiter, mock_redis):
        """Test rate limiting for Pro model."""
        result = await rate_limiter.check_and_consume("gemini-2.5-pro")
        assert result.allowed is True
        assert result.metadata.model == "gemini-2.5-pro"
    
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self, rate_limiter, mock_redis):
        """Test behavior when rate limit is exceeded."""
        # Mock Redis to return high usage count
        mock_redis.execute.return_value = [None, 10]  # High count
        
        result = await rate_limiter.check_and_consume("gemini-2.5-flash")
        assert result.allowed is False
        assert result.blocked_by is not None
        assert result.retry_after is not None
    
    @pytest.mark.asyncio
    async def test_execute_with_protection_success(self, rate_limiter, mock_redis):
        """Test successful execution with protection."""
        async def mock_api_call():
            return "success"
        
        result = await rate_limiter.execute_with_protection(
            "gemini-2.5-flash", 
            mock_api_call
        )
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_execute_with_protection_rate_limited(self, rate_limiter, mock_redis):
        """Test execution blocked by rate limiting."""
        # Mock rate limit exceeded
        mock_redis.execute.return_value = [None, 10]
        
        async def mock_api_call():
            return "success"
        
        with pytest.raises(RateLimitExceededException) as exc_info:
            await rate_limiter.execute_with_protection(
                "gemini-2.5-flash",
                mock_api_call
            )
        
        assert "gemini-2.5-flash" in str(exc_info.value)
        assert exc_info.value.model == "gemini-2.5-flash"
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_activation(self, rate_limiter, mock_redis):
        """Test circuit breaker activation after failures."""
        async def failing_api_call():
            raise Exception("API Error")
        
        # First failure should not open circuit
        with pytest.raises(Exception):
            await rate_limiter.execute_with_protection(
                "gemini-2.5-flash",
                failing_api_call
            )
        
        # Second failure should open circuit
        with pytest.raises(Exception):
            await rate_limiter.execute_with_protection(
                "gemini-2.5-flash", 
                failing_api_call
            )
        
        # Third call should be blocked by circuit breaker
        with pytest.raises(CircuitBreakerOpenException):
            await rate_limiter.execute_with_protection(
                "gemini-2.5-flash",
                failing_api_call
            )
    
    @pytest.mark.asyncio
    async def test_usage_stats(self, rate_limiter, mock_redis):
        """Test usage statistics retrieval."""
        # Mock Redis stats
        mock_redis.keys.return_value = [
            b"mb_sparrow_rl:flash:rpm",
            b"mb_sparrow_rl:flash:rpd", 
            b"mb_sparrow_rl:pro:rpm",
            b"mb_sparrow_rl:pro:rpd"
        ]
        mock_redis.zcard.return_value = 1
        
        stats = await rate_limiter.get_usage_stats()
        
        assert stats.flash_stats is not None
        assert stats.pro_stats is not None
        assert stats.flash_circuit is not None
        assert stats.pro_circuit is not None
        assert stats.uptime_percentage >= 0
        assert stats.total_requests_today >= 0
    
    @pytest.mark.asyncio
    async def test_health_check(self, rate_limiter, mock_redis):
        """Test comprehensive health check."""
        health = await rate_limiter.health_check()
        
        assert "overall" in health
        assert "redis" in health
        assert "circuit_breakers" in health
        assert "rate_limits" in health
        
        assert health["redis"] is True
        assert "flash" in health["circuit_breakers"]
        assert "pro" in health["circuit_breakers"]
    
    @pytest.mark.asyncio
    async def test_reset_limits(self, rate_limiter, mock_redis):
        """Test resetting rate limits."""
        # Reset specific model
        await rate_limiter.reset_limits("gemini-2.5-flash")
        mock_redis.delete.assert_called()
        
        # Reset all models
        await rate_limiter.reset_limits()
        # Should have called delete multiple times
        assert mock_redis.delete.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_invalid_model(self, rate_limiter):
        """Test handling of invalid model names."""
        with pytest.raises(ValueError):
            await rate_limiter.check_and_consume("invalid-model")
        
        with pytest.raises(ValueError):
            await rate_limiter.execute_with_protection(
                "invalid-model",
                lambda: "test"
            )
    
    @pytest.mark.asyncio
    async def test_redis_failure_handling(self, rate_limiter, mock_redis):
        """Test handling of Redis failures."""
        # Mock Redis failure
        mock_redis.pipeline.side_effect = Exception("Redis down")
        
        with pytest.raises(Exception):
            await rate_limiter.check_and_consume("gemini-2.5-flash")
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, rate_limiter, mock_redis):
        """Test handling of concurrent requests."""
        async def make_request():
            return await rate_limiter.check_and_consume("gemini-2.5-flash")
        
        # Make multiple concurrent requests
        tasks = [make_request() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed with mocked Redis
        for result in results:
            assert not isinstance(result, Exception)
            assert result.allowed is True
    
    @pytest.mark.asyncio
    async def test_safety_margin_application(self, mock_redis):
        """Test that safety margins are properly applied."""
        config = RateLimitConfig(
            flash_rpm_limit=10,
            flash_rpd_limit=100, 
            safety_margin=0.2  # 20% safety margin
        )
        
        with patch('redis.asyncio.from_url', return_value=mock_redis):
            limiter = GeminiRateLimiter(config)
            
            result = await limiter.check_and_consume("gemini-2.5-flash")
            
            # Effective limits should be 80% of configured limits
            assert result.metadata.rpm_limit == 8  # 10 * 0.8
            assert result.metadata.rpd_limit == 80  # 100 * 0.8
            
            await limiter.close()


class TestRateLimitConfiguration:
    """Test rate limit configuration management."""
    
    def test_config_from_environment(self):
        """Test configuration loading from environment."""
        with patch.dict('os.environ', {
            'GEMINI_FLASH_RPM_LIMIT': '15',
            'GEMINI_PRO_RPM_LIMIT': '5',
            'RATE_LIMIT_SAFETY_MARGIN': '0.1'
        }):
            config = RateLimitConfig.from_environment()
            assert config.flash_rpm_limit == 15
            assert config.pro_rpm_limit == 5
            assert config.safety_margin == 0.1
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Invalid safety margin
        with pytest.raises(ValueError):
            RateLimitConfig(safety_margin=1.5)
        
        # Invalid rate limits
        with pytest.raises(ValueError):
            RateLimitConfig(flash_rpm_limit=0)
        
        with pytest.raises(ValueError):
            RateLimitConfig(circuit_breaker_failure_threshold=0)
    
    def test_get_effective_limits(self):
        """Test getting effective limits for models."""
        config = RateLimitConfig()
        
        flash_rpm, flash_rpd = config.get_effective_limits("gemini-2.5-flash")
        assert flash_rpm == config.flash_rpm_limit
        assert flash_rpd == config.flash_rpd_limit
        
        pro_rpm, pro_rpd = config.get_effective_limits("gemini-2.5-pro")
        assert pro_rpm == config.pro_rpm_limit
        assert pro_rpd == config.pro_rpd_limit
        
        with pytest.raises(ValueError):
            config.get_effective_limits("unknown-model")
    
    def test_get_redis_keys(self):
        """Test Redis key generation."""
        config = RateLimitConfig(redis_key_prefix="test")
        
        rpm_key, rpd_key = config.get_redis_keys("gemini-2.5-flash")
        assert "test:gemini_2_5_flash" in rpm_key
        assert "test:gemini_2_5_flash" in rpd_key
        assert ":rpm" in rpm_key
        assert ":rpd" in rpd_key