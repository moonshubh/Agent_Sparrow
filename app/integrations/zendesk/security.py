import base64
import hmac
import time
from datetime import datetime, timezone
from hashlib import sha256
from typing import Optional


def verify_webhook_signature(
    *,
    signature_b64: Optional[str],
    timestamp: Optional[str],
    raw_body: bytes,
    signing_secret: Optional[str],
    tolerance_sec: int = 300,
) -> bool:
    """Verify Zendesk webhook authenticity.

    Zendesk docs: signature = base64(HMACSHA256(TIMESTAMP + BODY)) using the signing secret.
    Headers: X-Zendesk-Webhook-Signature, X-Zendesk-Webhook-Signature-Timestamp
    """
    if not signature_b64 or not timestamp or not signing_secret:
        return False

    # Keep the exact header string for HMAC and also parse for tolerance checks
    ts_header = str(timestamp)

    # Parse timestamp header: support both epoch seconds and ISO-8601 (e.g., 2025-10-15T09:00:00Z)
    ts_epoch: Optional[int] = None
    try:
        ts_epoch = int(ts_header)
    except Exception:
        try:
            ts_str = ts_header.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            ts_epoch = int(dt.timestamp())
        except Exception:
            return False

    now = int(time.time())
    if abs(now - ts_epoch) > max(1, int(tolerance_sec)):
        return False

    # HMAC uses the raw header string concatenated with the raw body
    message = ts_header.encode("utf-8") + raw_body
    expected = hmac.new(signing_secret.encode("utf-8"), message, sha256).digest()

    try:
        provided = base64.b64decode(signature_b64)
    except Exception:
        return False

    # constant-time compare
    return hmac.compare_digest(expected, provided)


def compute_expected_signature(timestamp: str, raw_body: bytes, signing_secret: str) -> str:
    """Compute Zendesk expected signature for debugging: base64(HMAC_SHA256(ts + raw_body)).
    Do not log full values; callers must scrub outputs before logging.
    """
    message = timestamp.encode("utf-8") + raw_body
    digest = hmac.new(signing_secret.encode("utf-8"), message, sha256).digest()
    return base64.b64encode(digest).decode("utf-8")
