"""
Router Configuration - Centralized pattern definitions and settings.

This module contains all routing patterns, thresholds, and mappings
to make the router more maintainable and configurable.
"""

import re
from typing import Dict, List, Pattern
from dataclasses import dataclass


@dataclass
class RouterConfig:
    """Configuration settings for the router."""
    confidence_threshold: float = 0.6
    embedding_confidence_threshold: float = 0.72
    smart_bypass_confidence: float = 0.95
    embedding_route_confidence: float = 0.85
    
    def __post_init__(self):
        """Validate configuration values."""
        # Validate confidence thresholds are between 0.0 and 1.0
        thresholds = [
            ('confidence_threshold', self.confidence_threshold),
            ('embedding_confidence_threshold', self.embedding_confidence_threshold),
            ('smart_bypass_confidence', self.smart_bypass_confidence),
            ('embedding_route_confidence', self.embedding_route_confidence)
        ]
        
        for name, value in thresholds:
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"{name} must be between 0.0 and 1.0, got {value}")
        
        # Initialize category mappings if not provided
        if self.category_mappings is None:
            self.category_mappings = {
                "log_analysis": "log_analyst",
                "primary_support": "primary_agent", 
                "research": "researcher"
            }
    
    # Category to destination mappings
    category_mappings: Dict[str, str] = None


class RouterPatterns:
    """Centralized pattern definitions for router bypass logic."""
    
    # HIGH PRIORITY: Obvious Mailbird technical issues -> primary_agent
    MAILBIRD_TECHNICAL_PATTERNS = [
        # Application startup/crash issues  
        r'\bmailbird\s+won\'?t\s+open\b',
        r'\bmailbird\s+bounces\b',
        r'\bmailbird\s+crashes\b',
        r'\bmailbird\s+won\'?t\s+start\b',
        r'\bmailbird\s+won\'?t\s+launch\b',
        r'\bmailbird\s+freezes\b',
        r'\bmailbird\s+not\s+working\b',
        r'\bmailbird\s+broken\b',
        r'\bmailbird\s+keeps\s+crashing\b',
        r'\bmailbird\s+crashing\b',
        r'\bfreezes\s+during\b',
        r'\bkeeps\s+freezing\b',
        
        # Email functionality issues
        r'\bemails?\s+not\s+loading\b',
        r'\bcan\'?t\s+send\s+emails?\b',
        r'\bcan\'?t\s+receive\s+emails?\b',
        r'\bsync\s+not\s+working\b',
        r'\bmailbird\s+slow\b',
        r'\bmailbird\s+error\b',
        r'\bconnection\s+problems?\b',
        r'\blogin\s+failed\b',
        r'\boauth\s+authentication\b',
        r'\bssl\s+handshake\s+failed\b',
        r'\boffice\s+365\s+accounts?\b',
        
        # Account/setup issues with Mailbird context
        r'\badd\s+accounts?\s+to\s+mailbird\b',
        r'\bsetup\s+mailbird\b',
        r'\bconfigure\s+mailbird\b',
        r'\bmailbird\s+settings\b'
    ]
    
    # Log file keywords -> log_analyst  
    LOG_PATTERNS = [
        r'\blog\s+files?\b',
        r'\bcrash\s+logs?\b',
        r'\bdebug\s+logs?\b',
        r'\berror\s+logs?\b',
        r'\bmailbird\.log\b',
        r'\bhere\'?s\s+my\s+logs?\b',
        r'\battached\s+logs?\b',
        r'\blogs?\s+shows?\b',
        r'\bcheck\s+my\s+logs?\b'
    ]
    
    # Research-type queries -> researcher
    RESEARCH_PATTERNS = [
        r'\bwhat\s+is\s+the\s+latest\b',
        r'\brecent\s+updates?\b',
        r'\bnew\s+features?\b',
        r'\bchangelogs?\b',
        r'\bcompared\s+to\s+others?\b',
        r'\bbest\s+practices\b',
        r'\bindustry\s+standards?\b',
        r'\balternatives?\s+to\b',
        # Domain-specific research patterns
        r'\bemail\s+client\s+comparison\b',
        r'\bmailbird\s+vs\s+\w+\b',
        r'\bmarket\s+analysis\b',
        r'\bcompetitor\s+features\b',
        r'\bindustry\s+trends\b',
        r'\bemail\s+standards\b',
        r'\bsecurity\s+protocols\b',
        r'\bprivacy\s+policies\b'
    ]
    
    # General Mailbird question patterns
    GENERAL_MAILBIRD_PATTERNS = [
        r'\bhow\s+to\b',
        r'\bhow\s+do\s+i\b',
        r'\bhelp\s+with\b',
        r'\bproblems?\s+with\b',
        r'\bissues?\s+with\b',
        r'\bquestions?\s+about\b'
    ]
    
    @classmethod
    def compile_patterns(cls) -> Dict[str, List[Pattern]]:
        """Compile all regex patterns for efficiency."""
        return {
            'mailbird_technical': [re.compile(pattern, re.IGNORECASE) for pattern in cls.MAILBIRD_TECHNICAL_PATTERNS],
            'log': [re.compile(pattern, re.IGNORECASE) for pattern in cls.LOG_PATTERNS],
            'research': [re.compile(pattern, re.IGNORECASE) for pattern in cls.RESEARCH_PATTERNS],
            'general_mailbird': [re.compile(pattern, re.IGNORECASE) for pattern in cls.GENERAL_MAILBIRD_PATTERNS]
        }


class ComplexityPatterns:
    """Patterns for query complexity calculation."""
    
    TECHNICAL_TERMS = [
        'oauth', 'imap', 'smtp', 'ssl', 'tls', 'certificate', 'token',
        'authentication', 'synchronization', 'indexing', 'database',
        'memory leak', 'cpu usage', 'performance', 'latency', 'timeout'
    ]
    
    ERROR_PATTERNS = [
        'error', 'exception', 'failed', 'crash', 'stack trace',
        'debug', 'warning', 'critical', 'fatal'
    ]
    
    MULTIPLE_ISSUE_INDICATORS = [
        'and also', 'additionally', 'furthermore', 'moreover'
    ]
    
    COMPLEX_SCENARIOS = {
        'oauth_loop': {
            'primary_terms': ['oauth'],
            'secondary_terms': ['loop', 'redirect', 'infinite', 'stuck'],
            'weight': 1.5
        },
        'performance_issue': {
            'primary_terms': ['performance'],
            'secondary_terms': ['slow', 'lag', 'freeze', 'hang', 'unresponsive'],
            'weight': 1.3
        },
        'sync_failure': {
            'primary_terms': ['sync', 'synchronization'],
            'secondary_terms': ['failed', 'error', 'timeout', 'incomplete'],
            'weight': 1.4
        },
        'memory_leak': {
            'primary_terms': ['memory'],
            'secondary_terms': ['leak', 'usage', 'high', 'consuming'],
            'weight': 1.6
        },
        'network_connectivity': {
            'primary_terms': ['connection', 'network'],
            'secondary_terms': ['timeout', 'failed', 'refused', 'unreachable'],
            'weight': 1.2
        }
    }


# Global configuration instance
DEFAULT_ROUTER_CONFIG = RouterConfig()