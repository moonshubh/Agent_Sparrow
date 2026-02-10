"""
FeedMe endpoint-level authorization helpers.

Read endpoints remain open, while mutation endpoints require an admin role
derived from JWT claims.
"""

from __future__ import annotations

from typing import Iterable

from fastapi import Depends, HTTPException, status

from app.core.security import TokenPayload, get_current_user

_ADMIN_ROLE_CANDIDATES: set[str] = {
    "admin",
    "super_admin",
    "owner",
    "feedme_admin",
    "service_role",
}


def _normalized_roles(roles: Iterable[str] | None) -> set[str]:
    if not roles:
        return set()
    normalized: set[str] = set()
    for role in roles:
        role_value = (role or "").strip().lower()
        if role_value:
            normalized.add(role_value)
    return normalized


def has_feedme_admin_role(user: TokenPayload) -> bool:
    """Return True when the user has any accepted admin role claim."""
    return bool(_normalized_roles(user.roles) & _ADMIN_ROLE_CANDIDATES)


async def require_feedme_admin(
    current_user: TokenPayload = Depends(get_current_user),
) -> TokenPayload:
    """
    Dependency for FeedMe mutation endpoints.

    Uses JWT role claims from `app.core.security.get_current_user`.
    """
    if not has_feedme_admin_role(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="FeedMe mutation requires admin role",
        )
    return current_user

