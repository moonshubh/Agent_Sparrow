"""
Database models for the MB-Sparrow application.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class UserAPIKey(Base):
    """
    Stores encrypted API keys for users.
    Each user can have one API key per provider type.
    """
    __tablename__ = "user_api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    api_key_type = Column(String(50), nullable=False, index=True)
    encrypted_key = Column(Text, nullable=False)
    key_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "api_key_type IN ('gemini', 'openai', 'tavily', 'firecrawl')",
            name="valid_api_key_type"
        ),
        CheckConstraint(
            "LENGTH(encrypted_key) > 0",
            name="non_empty_encrypted_key"
        ),
        CheckConstraint(
            "LENGTH(user_id) > 0",
            name="non_empty_user_id"
        ),
        Index('idx_user_api_key_unique', 'user_id', 'api_key_type', unique=True),
    )

class APIKeyAuditLog(Base):
    """
    Audit log for API key operations.
    Does not store sensitive data, only operation metadata.
    """
    __tablename__ = "api_key_audit_log"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    api_key_type = Column(String(50), nullable=False, index=True)
    operation = Column(String(50), nullable=False, index=True)
    operation_details = Column(JSONB, nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "operation IN ('CREATE', 'UPDATE', 'DELETE', 'USE', 'VALIDATE')",
            name="valid_audit_operation"
        ),
        CheckConstraint(
            "LENGTH(user_id) > 0",
            name="non_empty_audit_user_id"
        ),
    )

# Additional models for existing functionality can be added here
# For example, if you have User, Session, or other models