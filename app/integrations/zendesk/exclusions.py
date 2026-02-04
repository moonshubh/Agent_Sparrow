from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class TicketExclusion:
    excluded: bool
    reason: str | None
    details: dict[str, Any]


def _normalize_str_set(items: Iterable[Any] | None) -> set[str]:
    if not items:
        return set()
    out: set[str] = set()
    for item in items:
        try:
            s = str(item).strip().lower()
        except Exception:
            continue
        if s:
            out.add(s)
    return out


def _normalize_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [
            str(t).strip() for t in raw if isinstance(t, (str, int)) and str(t).strip()
        ]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        if "," in s:
            return [t.strip() for t in s.split(",") if t.strip()]
        return [t.strip() for t in s.split() if t.strip()]
    return []


def compute_ticket_exclusion(
    ticket: dict[str, Any] | None,
    *,
    brand_id: str | None = None,
    excluded_statuses: Iterable[Any] = (),
    excluded_tags: Iterable[Any] = (),
    excluded_brand_ids: Iterable[Any] = (),
) -> TicketExclusion:
    t = ticket or {}

    status = str(t.get("status") or "").strip().lower()
    excluded_status_set = _normalize_str_set(excluded_statuses)
    if status and status in excluded_status_set:
        return TicketExclusion(
            excluded=True,
            reason=f"status:{status}",
            details={"status": status},
        )

    tags = _normalize_tags(t.get("tags"))
    excluded_tag_set = _normalize_str_set(excluded_tags)
    for tag in tags:
        lt = tag.strip().lower()
        if lt and lt in excluded_tag_set:
            return TicketExclusion(
                excluded=True,
                reason=f"tag:{lt}",
                details={"matched_tag": lt},
            )

    resolved_brand_id = None
    try:
        resolved_brand_id = str(brand_id).strip() if brand_id is not None else None
    except Exception:
        resolved_brand_id = None
    if not resolved_brand_id:
        try:
            resolved_brand_id = str(t.get("brand_id") or "").strip() or None
        except Exception:
            resolved_brand_id = None
    excluded_brand_set = {str(b).strip() for b in excluded_brand_ids if str(b).strip()}
    if resolved_brand_id and resolved_brand_id in excluded_brand_set:
        return TicketExclusion(
            excluded=True,
            reason=f"brand_id:{resolved_brand_id}",
            details={"brand_id": resolved_brand_id},
        )

    return TicketExclusion(excluded=False, reason=None, details={})
