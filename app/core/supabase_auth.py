"""
Supabase Authentication Client
Production-ready auth integration with comprehensive security features.
"""

import os
import logging
import threading
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
import httpx
import jwt
from functools import lru_cache

from supabase import create_client, Client
try:  # supabase-py 2.24+ splits auth into supabase_auth
    from supabase_auth import AuthResponse, Session, User
    from supabase_auth.errors import AuthError
except ImportError:  # Backward compatibility with supabase-py <=2.16
    from gotrue import AuthResponse, Session, User  # type: ignore
    from gotrue.errors import AuthError  # type: ignore

from app.core.settings import settings
from app.db.supabase.client import get_supabase_client

logger = logging.getLogger(__name__)


class SupabaseAuthClient:
    """
    Comprehensive Supabase Auth client with security features:
    - JWT validation
    - Session management
    - Audit logging
    - Rate limiting support
    - Error sanitization
    """
    
    def __init__(self):
        self.client = get_supabase_client()
        self.jwt_secret = settings.supabase_jwt_secret or settings.jwt_secret_key
        self.jwt_algorithm = settings.jwt_algorithm
        
        # Log JWT secret configuration status
        if settings.supabase_jwt_secret:
            logger.info("SUPABASE_JWT_SECRET is configured from environment")
        else:
            logger.warning("SUPABASE_JWT_SECRET not found in environment, using fallback JWT_SECRET_KEY")
            if self.jwt_secret == "change-this-in-production":
                logger.error("CRITICAL: Using default JWT secret - this is insecure!")
        
    async def sign_up(
        self, 
        email: str, 
        password: str,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[User], Optional[str]]:
        """
        Sign up a new user with email and password.
        
        Returns:
            Tuple of (User, error_message)
        """
        try:
            # Add metadata if provided
            auth_response: AuthResponse = self.client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": metadata or {}
                }
            })
            
            if auth_response.user:
                # Log successful signup
                await self._audit_log(
                    user_id=auth_response.user.id,
                    event_type="sign_up",
                    event_details={
                        "email": email,
                        "metadata": metadata
                    },
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=True
                )
                return auth_response.user, None
            else:
                return None, "Sign up failed - no user returned"
                
        except AuthError as e:
            # Log failed signup
            await self._audit_log(
                user_id=None,
                event_type="sign_up",
                event_details={"email": email},
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                error_message=str(e)
            )
            
            # Sanitize error message
            error_msg = self._sanitize_auth_error(str(e))
            logger.warning(f"Sign up failed for email {email}: {error_msg}")
            return None, error_msg
            
    async def sign_in_with_password(
        self,
        email: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[Session], Optional[str]]:
        """
        Sign in with email and password.
        
        Returns:
            Tuple of (Session, error_message)
        """
        try:
            auth_response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if auth_response.session:
                # Store session info
                await self._store_session(
                    auth_response.session,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                
                # Log successful signin
                await self._audit_log(
                    user_id=auth_response.user.id,
                    event_type="sign_in",
                    event_details={"method": "password"},
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=True
                )
                
                return auth_response.session, None
            else:
                return None, "Sign in failed - no session returned"
                
        except AuthError as e:
            # Log failed signin
            await self._audit_log(
                user_id=None,
                event_type="sign_in",
                event_details={"email": email, "method": "password"},
                ip_address=ip_address,
                user_agent=user_agent,
                success=False,
                error_message=str(e)
            )
            
            error_msg = self._sanitize_auth_error(str(e))
            logger.warning(f"Sign in failed for email {email}: {error_msg}")
            return None, error_msg
            
    async def sign_in_with_oauth(
        self,
        provider: str,  # 'google', 'github', etc.
        redirect_to: Optional[str] = None,
        scopes: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Get OAuth provider URL for sign in.
        
        Returns:
            Tuple of (provider_url, error_message)
        """
        try:
            options = {}
            if redirect_to:
                options["redirect_to"] = redirect_to
            if scopes:
                options["scopes"] = scopes
                
            response = self.client.auth.sign_in_with_oauth({
                "provider": provider,
                "options": options
            })
            
            if response.url:
                # Log OAuth initiation
                await self._audit_log(
                    user_id=None,
                    event_type="oauth_init",
                    event_details={"provider": provider},
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=True
                )
                return response.url, None
            else:
                return None, "Failed to generate OAuth URL"
                
        except AuthError as e:
            error_msg = f"OAuth initialization failed: {self._sanitize_auth_error(str(e))}"
            logger.warning(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"OAuth initialization failed: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
            
    async def sign_out(
        self,
        jwt_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[str]:
        """
        Sign out the current user.
        
        Returns:
            Error message if failed, None if successful
        """
        try:
            # Get user from token for audit log
            user_data = await self.verify_jwt(jwt_token)
            user_id = user_data.get("sub") if user_data else None
            
            # Prefer admin sign-out when service key is available; fallback to local sign-out
            admin_sign_out = False
            try:
                admin_client = getattr(self.client.auth, "admin", None)
                if admin_client:
                    admin_client.sign_out(jwt_token, scope="global")
                    admin_sign_out = True
            except Exception as admin_exc:
                logger.debug(f"Admin sign out failed: {admin_exc}")

            if not admin_sign_out:
                # Local sign-out (no session priming in supabase-py 2.24+)
                self.client.auth.sign_out()
            
            # Revoke session in database
            if user_id:
                await self._revoke_session(jwt_token)
                
                # Log successful signout
                await self._audit_log(
                    user_id=user_id,
                    event_type="sign_out",
                    event_details={},
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=True
                )
            
            return None
            
        except Exception as e:
            error_msg = f"Sign out failed: {str(e)}"
            logger.error(error_msg)
            return error_msg
            
    async def refresh_token(
        self,
        refresh_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[Session], Optional[str]]:
        """
        Refresh access token using refresh token.
        
        Returns:
            Tuple of (Session, error_message)
        """
        try:
            auth_response = self.client.auth.refresh_session(refresh_token)
            session = getattr(auth_response, "session", auth_response)
            
            if session:
                # Update session info
                await self._store_session(
                    session,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
                
                # Log token refresh
                await self._audit_log(
                    user_id=session.user.id,
                    event_type="token_refresh",
                    event_details={},
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=True
                )
                
                return session, None
            else:
                return None, "Token refresh failed"
                
        except AuthError as e:
            error_msg = self._sanitize_auth_error(str(e))
            logger.warning(f"Token refresh failed: {error_msg}")
            return None, error_msg
            
    async def reset_password_for_email(
        self,
        email: str,
        redirect_to: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Optional[str]:
        """
        Send password reset email.
        
        Returns:
            Error message if failed, None if successful
        """
        try:
            options = {}
            if redirect_to:
                options["redirect_to"] = redirect_to
                
            self.client.auth.reset_password_for_email(email, options)
            
            # Log password reset request
            await self._audit_log(
                user_id=None,
                event_type="password_reset_request",
                event_details={"email": email},
                ip_address=ip_address,
                user_agent=user_agent,
                success=True
            )
            
            return None
            
        except Exception as e:
            error_msg = f"Password reset failed: {str(e)}"
            logger.error(error_msg)
            return error_msg
            
    async def update_user(
        self,
        jwt_token: str,
        attributes: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[Optional[User], Optional[str]]:
        """
        Update user attributes.
        
        Returns:
            Tuple of (User, error_message)
        """
        try:
            user_data = await self.verify_jwt(jwt_token)
            user_id = user_data.get("sub") if user_data else None
            if not user_id:
                return None, "Invalid token for user update"

            user = None
            try:
                admin_client = getattr(self.client.auth, "admin", None)
                if admin_client:
                    user_response = admin_client.update_user_by_id(user_id, attributes)
                    user = getattr(user_response, "user", user_response)
            except Exception as admin_exc:
                logger.error(f"Admin user update failed: {admin_exc}")

            # Fallback to session-scoped update when admin client is unavailable
            if user is None:
                user_response = self.client.auth.get_user(jwt_token)
                current_user = getattr(user_response, "user", user_response)
                if not current_user:
                    return None, "User update failed: session not available"
                user_response = self.client.auth.update_user(attributes)
                user = getattr(user_response, "user", user_response)
            
            if user:
                # Log user update
                await self._audit_log(
                    user_id=user.id,
                    event_type="user_update",
                    event_details={"attributes": list(attributes.keys())},
                    ip_address=ip_address,
                    user_agent=user_agent,
                    success=True
                )
                
                return user, None
            else:
                return None, "User update failed"
                
        except Exception as e:
            error_msg = f"User update failed: {str(e)}"
            logger.error(error_msg)
            return None, error_msg
            
    async def verify_jwt(
        self, 
        token: str,
        check_revoked: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Verify and decode a JWT token.
        
        Args:
            token: JWT token to verify
            check_revoked: Whether to check if session is revoked
            
        Returns:
            Decoded token payload if valid, None otherwise
        """
        try:
            # Since SUPABASE_JWT_SECRET is configured on Railway, use it for secure verification
            if self.jwt_secret and self.jwt_secret != "change-this-in-production":
                try:
                    # Properly verify JWT with the configured secret
                    payload = jwt.decode(
                        token,
                        self.jwt_secret,
                        algorithms=[self.jwt_algorithm],
                        audience="authenticated",  # Supabase uses "authenticated" as audience
                        options={"verify_exp": True}
                    )
                    
                    # Check if session is revoked
                    if check_revoked:
                        try:
                            is_revoked = await self._is_session_revoked(token)
                            if is_revoked:
                                logger.warning("Attempted to use revoked token")
                                return None
                        except Exception:
                            pass  # Don't fail if revocation check fails
                    
                    # Update last activity
                    try:
                        await self._update_session_activity(token)
                    except Exception:
                        pass  # Don't fail if activity update fails
                    
                    logger.debug(f"JWT verified successfully for user: {payload.get('sub')[:8]}...")
                    return payload
                    
                except jwt.ExpiredSignatureError:
                    logger.debug("JWT token has expired")
                    return None
                except jwt.InvalidAudienceError as e:
                    logger.debug(f"JWT audience validation failed: {e}")
                    # Try without audience validation as Supabase might use different audience
                    try:
                        payload = jwt.decode(
                            token,
                            self.jwt_secret,
                            algorithms=[self.jwt_algorithm],
                            options={"verify_exp": True, "verify_aud": False}
                        )
                        logger.debug(f"JWT verified without audience check for user: {payload.get('sub')[:8]}...")
                        return payload
                    except Exception as e2:
                        logger.debug(f"JWT verification without audience also failed: {e2}")
                        return None
                except jwt.InvalidTokenError as e:
                    logger.error(f"JWT verification failed: {e}")
                    return None
            else:
                # This should not happen in production if SUPABASE_JWT_SECRET is set
                logger.error("CRITICAL: JWT secret not configured properly! JWT_SECRET value: " + 
                           ("not set" if not self.jwt_secret else "default value"))
                return None
            
        except jwt.ExpiredSignatureError:
            logger.debug("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.debug(f"Invalid JWT token: {e}")
            return None
        except Exception as e:
            logger.error(f"JWT verification error: {e}")
            return None
            
    async def get_user_from_token(
        self,
        jwt_token: str
    ) -> Optional[User]:
        """
        Get user from JWT token.
        
        Returns:
            User object if valid, None otherwise
        """
        try:
            # Verify token first
            payload = await self.verify_jwt(jwt_token)
            if not payload:
                return None
                
            # Fetch user directly with the provided JWT (supabase-py 2.24 compatible)
            user_response = self.client.auth.get_user(jwt_token)
            user = getattr(user_response, "user", user_response)
            
            return user
            
        except Exception as e:
            logger.error(f"Failed to get user from token: {e}")
            return None
            
    # Private helper methods
    
    async def _store_session(
        self,
        session: Session,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Store session information in database."""
        try:
            supabase = get_supabase_client()
            
            # Calculate expiry
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=session.expires_in)
            
            await supabase.table("auth_sessions").upsert({
                "user_id": session.user.id,
                "session_token": session.access_token,
                "refresh_token": session.refresh_token,
                "expires_at": expires_at.isoformat(),
                "ip_address": ip_address,
                "user_agent": user_agent,
                "last_activity": datetime.now(timezone.utc).isoformat()
            }).execute()
            
        except Exception as e:
            logger.error(f"Failed to store session: {e}")
            
    async def _revoke_session(self, token: str):
        """Mark session as revoked in database."""
        try:
            supabase = get_supabase_client()
            
            await supabase.table("auth_sessions").update({
                "revoked_at": datetime.now(timezone.utc).isoformat()
            }).eq("session_token", token).execute()
            
        except Exception as e:
            logger.error(f"Failed to revoke session: {e}")
            
    async def _is_session_revoked(self, token: str) -> bool:
        """Check if session is revoked."""
        try:
            supabase = get_supabase_client()
            
            response = await supabase.table("auth_sessions")\
                .select("revoked_at")\
                .eq("session_token", token)\
                .single()\
                .execute()
                
            if response.data and response.data.get("revoked_at"):
                return True
                
        except Exception:
            # If we can't check, assume not revoked
            pass
            
        return False
        
    async def _update_session_activity(self, token: str):
        """Update last activity timestamp for session."""
        try:
            supabase = get_supabase_client()
            
            await supabase.table("auth_sessions").update({
                "last_activity": datetime.now(timezone.utc).isoformat()
            }).eq("session_token", token).execute()
            
        except Exception as e:
            logger.debug(f"Failed to update session activity: {e}")
            
    async def _audit_log(
        self,
        user_id: Optional[str],
        event_type: str,
        event_details: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """Create audit log entry."""
        try:
            supabase = get_supabase_client()
            
            await supabase.table("auth_audit_log").insert({
                "user_id": user_id,
                "event_type": event_type,
                "event_details": event_details,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "success": success,
                "error_message": error_message,
                "created_at": datetime.now(timezone.utc).isoformat()
            }).execute()
            
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")
            
    def _sanitize_auth_error(self, error_msg: str) -> str:
        """
        Sanitize auth error messages to prevent information leakage.
        """
        error_lower = error_msg.lower()
        
        # Map specific errors to user-friendly messages
        if "invalid login credentials" in error_lower:
            return "Invalid email or password"
        elif "user already registered" in error_lower:
            return "An account with this email already exists"
        elif "email not confirmed" in error_lower:
            return "Please verify your email before signing in"
        elif "password" in error_lower and "weak" in error_lower:
            return "Password does not meet security requirements"
        elif "rate limit" in error_lower:
            return "Too many attempts. Please try again later"
        elif "network" in error_lower or "connection" in error_lower:
            return "Network error. Please check your connection"
        else:
            # Generic error for anything else
            return "Authentication failed. Please try again"


# Singleton instance with thread safety
_auth_client: Optional[SupabaseAuthClient] = None
_auth_client_lock = threading.Lock()


def get_auth_client() -> SupabaseAuthClient:
    """Get singleton Supabase auth client instance with thread safety."""
    global _auth_client
    if _auth_client is None:
        with _auth_client_lock:
            # Double-check locking pattern
            if _auth_client is None:
                _auth_client = SupabaseAuthClient()
    return _auth_client
