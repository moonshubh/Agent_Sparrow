"""
Tests for TokenBucket rate limiting algorithm.
"""

import pytest
import asyncio
import time
from unittest.mock import patch

from app.core.rate_limiting.token_bucket import TokenBucket


class TestTokenBucket:
    """Test cases for TokenBucket rate limiter."""
    
    def test_initialization(self):
        """Test TokenBucket initialization."""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        
        assert bucket.capacity == 10
        assert bucket.refill_rate == 2.0
        assert bucket.tokens == 10  # Starts full
        assert bucket.last_refill is not None
    
    def test_initialization_invalid_params(self):
        """Test TokenBucket initialization with invalid parameters."""
        with pytest.raises(ValueError):
            TokenBucket(capacity=0, refill_rate=1.0)
        
        with pytest.raises(ValueError):
            TokenBucket(capacity=10, refill_rate=-1.0)
    
    @pytest.mark.asyncio
    async def test_consume_single_token(self):
        """Test consuming a single token."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        
        # Should succeed
        result = await bucket.consume(1)
        assert result is True
        assert bucket.tokens == 9
    
    @pytest.mark.asyncio
    async def test_consume_multiple_tokens(self):
        """Test consuming multiple tokens."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        
        # Should succeed
        result = await bucket.consume(5)
        assert result is True
        assert bucket.tokens == 5
    
    @pytest.mark.asyncio
    async def test_consume_more_than_available(self):
        """Test consuming more tokens than available."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        
        # Consume most tokens
        await bucket.consume(9)
        assert abs(bucket.tokens - 1.0) < 0.01  # Allow for floating point precision
        
        # Try to consume more than available
        result = await bucket.consume(5)
        assert result is False
        assert abs(bucket.tokens - 1.0) < 0.01  # Should remain approximately unchanged
    
    @pytest.mark.asyncio
    async def test_consume_exact_capacity(self):
        """Test consuming exactly the bucket capacity."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        
        result = await bucket.consume(10)
        assert result is True
        assert bucket.tokens == 0
    
    @pytest.mark.asyncio
    async def test_refill_over_time(self):
        """Test token refill over time."""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)  # 2 tokens per second
        
        # Consume all tokens
        await bucket.consume(10)
        assert bucket.tokens == 0
        
        # Manually set last_refill to 1 second ago
        bucket.last_refill = time.time() - 1.0
        
        # Refill should add 2 tokens (2 tokens/second * 1 second)
        await bucket._refill()
        assert abs(bucket.tokens - 2.0) < 0.1  # Allow for timing precision
    
    @pytest.mark.asyncio
    async def test_refill_does_not_exceed_capacity(self):
        """Test that refill doesn't exceed bucket capacity."""
        bucket = TokenBucket(capacity=10, refill_rate=5.0)  # 5 tokens per second
        
        # Start with some tokens
        bucket.tokens = 8
        
        # Mock time advancement
        with patch('time.time') as mock_time:
            # Simulate 1 second passing (would add 5 tokens)
            mock_time.side_effect = [bucket.last_refill, bucket.last_refill + 1.0]
            
            await bucket._refill()
            # Should cap at capacity (10), not exceed to 13
            assert bucket.tokens == 10
    
    @pytest.mark.asyncio
    async def test_refill_fractional_time(self):
        """Test refill with fractional time periods."""
        bucket = TokenBucket(capacity=10, refill_rate=4.0)  # 4 tokens per second
        
        # Consume all tokens
        await bucket.consume(10)
        assert bucket.tokens == 0
        
        # Mock time advancement
        with patch('time.time') as mock_time:
            # Simulate 0.5 seconds passing
            mock_time.side_effect = [bucket.last_refill, bucket.last_refill + 0.5]
            
            # Should add 2 tokens (4 tokens/second * 0.5 seconds)
            await bucket._refill()
            assert bucket.tokens == 2.0
    
    @pytest.mark.asyncio
    async def test_consume_after_refill(self):
        """Test consuming tokens after refill."""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        
        # Consume all tokens
        await bucket.consume(10)
        assert bucket.tokens == 0
        
        # Mock time advancement
        with patch('time.time') as mock_time:
            mock_time.side_effect = [
                bucket.last_refill,
                bucket.last_refill + 2.0,  # 2 seconds later
                bucket.last_refill + 2.0   # Called again during consume
            ]
            
            # Should be able to consume after refill
            result = await bucket.consume(3)
            assert result is True
            # 4 tokens refilled (2 tokens/sec * 2 sec), 3 consumed
            assert bucket.tokens == 1.0
    
    @pytest.mark.asyncio
    async def test_burst_capacity(self):
        """Test burst capacity functionality."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0, burst_capacity=15)
        
        # Should start with burst capacity
        assert bucket.tokens == 15
        
        # Should be able to consume up to burst capacity
        result = await bucket.consume(15)
        assert result is True
        assert bucket.tokens == 0
    
    @pytest.mark.asyncio
    async def test_get_current_tokens(self):
        """Test getting current token count."""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        
        # Consume some tokens
        await bucket.consume(3)
        
        current_tokens = await bucket.get_current_tokens()
        # Should be approximately 7 (allowing for small time passage)
        assert abs(current_tokens - 7.0) < 0.5
    
    @pytest.mark.asyncio
    async def test_time_until_tokens_available(self):
        """Test calculating time until tokens are available."""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        
        # Consume all tokens
        await bucket.consume(10)
        
        # Time until 5 tokens are available
        time_until = await bucket.time_until_tokens_available(5)
        assert time_until == 2.5  # 5 tokens / 2 tokens per second
    
    @pytest.mark.asyncio
    async def test_time_until_tokens_already_available(self):
        """Test time calculation when tokens are already available."""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        
        # We have 10 tokens, asking for 5
        time_until = await bucket.time_until_tokens_available(5)
        assert time_until == 0.0
    
    def test_str_representation(self):
        """Test string representation of TokenBucket."""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        
        str_repr = str(bucket)
        assert "10.0/10" in str_repr
        assert "2.0 tokens/sec" in str_repr