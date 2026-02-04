"""
Production-Ready Human Approval Workflow for FeedMe Extracted Text
Handles the approval process for PDF OCR and manually entered text

Features:
- Secure approval workflow with role-based access control
- Batch processing capabilities for efficiency
- Comprehensive audit logging
- Real-time notifications and webhooks
- Automated quality checks and suggestions
- Production monitoring and metrics
"""

import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass, asdict, field
import hashlib
import re

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from app.feedme.schemas import ProcessingStatus, ApprovalStatus, ProcessingMethod
from app.core.auth import verify_user_permission
from app.core.notifications import NotificationService

# Configure production logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger(__name__)

# Production constants
MAX_BATCH_SIZE = int(os.getenv("FEEDME_APPROVAL_BATCH_SIZE", "100"))
APPROVAL_TIMEOUT_HOURS = int(os.getenv("FEEDME_APPROVAL_TIMEOUT_HOURS", "72"))
AUTO_APPROVE_CONFIDENCE = float(os.getenv("FEEDME_AUTO_APPROVE_CONFIDENCE", "0.95"))
MIN_TEXT_LENGTH = int(os.getenv("FEEDME_MIN_TEXT_LENGTH", "50"))
MAX_TEXT_LENGTH = int(os.getenv("FEEDME_MAX_TEXT_LENGTH", "1000000"))


class ApprovalAction(str, Enum):
    """Actions that can be taken during approval workflow"""

    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_REPROCESS = "request_reprocess"
    EDIT_AND_APPROVE = "edit_and_approve"
    AUTO_APPROVE = "auto_approve"
    ESCALATE = "escalate"
    BATCH_APPROVE = "batch_approve"
    BATCH_REJECT = "batch_reject"


class ApprovalPriority(str, Enum):
    """Priority levels for approval queue"""

    CRITICAL = "critical"  # Requires immediate attention
    HIGH = "high"  # Low confidence or quality issues
    MEDIUM = "medium"  # Standard review
    LOW = "low"  # High confidence, routine
    AUTO = "auto"  # Can be auto-approved


class ReviewerRole(str, Enum):
    """Roles for approval workflow"""

    ADMIN = "admin"  # Full access
    SENIOR_REVIEWER = "senior"  # Can approve all, handle escalations
    REVIEWER = "reviewer"  # Standard approval rights
    VIEWER = "viewer"  # Read-only access


@dataclass
class ApprovalDecision:
    """Represents a human approval decision with enhanced metadata"""

    conversation_id: int
    action: ApprovalAction
    reviewer_id: str
    reviewer_role: ReviewerRole
    notes: Optional[str] = None
    edited_text: Optional[str] = None
    feedback: Optional[str] = None
    quality_score: Optional[float] = None
    confidence_score: Optional[float] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["action"] = self.action.value
        data["reviewer_role"] = self.reviewer_role.value
        return data

    def calculate_decision_hash(self) -> str:
        """Calculate unique hash for this decision"""
        content = f"{self.conversation_id}:{self.action.value}:{self.reviewer_id}:{self.timestamp.isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class QualityMetrics:
    """Quality metrics for text evaluation"""

    readability_score: float  # 0-1
    completeness_score: float  # 0-1
    formatting_score: float  # 0-1
    language_quality: float  # 0-1
    overall_score: float  # 0-1
    issues: List[str]
    suggestions: List[str]


class HumanApprovalWorkflow:
    """
    Production-ready human approval workflow for extracted text

    Features:
    - Present extracted text with processing metadata for review
    - Allow approval, rejection, or editing of extracted text
    - Track approval history and feedback with audit trail
    - Handle re-processing requests
    - Batch processing capabilities
    - Automated quality checks and suggestions
    - Real-time notifications and webhooks
    - Role-based access control
    - Production monitoring and metrics
    """

    def __init__(
        self,
        supabase_client=None,
        notification_service: Optional[NotificationService] = None,
    ):
        self.supabase_client = supabase_client
        self.notification_service = notification_service or NotificationService()

        # Caches for performance
        self._quality_cache: Dict[str, Any] = {}
        self._user_role_cache: Dict[str, Any] = {}

        # Metrics tracking
        self.metrics = {
            "decisions_processed": 0,
            "auto_approvals": 0,
            "manual_approvals": 0,
            "rejections": 0,
            "escalations": 0,
            "average_review_time": 0.0,
        }

        # Webhook configuration
        self.webhook_url = os.getenv("FEEDME_APPROVAL_WEBHOOK_URL")
        self.webhook_enabled = bool(self.webhook_url)

    async def verify_reviewer_permission(
        self,
        reviewer_id: str,
        action: ApprovalAction,
        conversation_id: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Verify if reviewer has permission for the action"""
        # Check cache first
        cache_key = f"{reviewer_id}:{action.value}"
        if cache_key in self._user_role_cache:
            role = self._user_role_cache[cache_key]
        else:
            # Get user role from auth service
            try:
                role = await verify_user_permission(reviewer_id, "feedme.approval")
                self._user_role_cache[cache_key] = role
            except Exception as e:
                logger.error(f"Failed to verify user permission: {e}")
                return False, "Permission verification failed"

        # Check role-based permissions
        if role == ReviewerRole.ADMIN:
            return True, None

        if role == ReviewerRole.SENIOR_REVIEWER:
            return True, None

        if role == ReviewerRole.REVIEWER:
            # Regular reviewers can't handle escalations or batch operations
            if action in [
                ApprovalAction.ESCALATE,
                ApprovalAction.BATCH_APPROVE,
                ApprovalAction.BATCH_REJECT,
            ]:
                return False, "Insufficient permissions for this action"
            return True, None

        if role == ReviewerRole.VIEWER:
            return False, "View-only access"

        return False, "Unknown role"

    async def get_pending_approvals(
        self,
        limit: int = 20,
        offset: int = 0,
        processing_method: Optional[ProcessingMethod] = None,
        priority: Optional[ApprovalPriority] = None,
        reviewer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get conversations pending approval

        Args:
            limit: Maximum number of conversations to return
            offset: Offset for pagination
            processing_method: Filter by processing method (pdf_ocr, manual_text, etc.)

        Returns:
            Dict with conversations and metadata
        """
        try:
            # Build filter conditions
            filters = {
                "processing_status": ProcessingStatus.COMPLETED.value,
                "approval_status": ApprovalStatus.PENDING.value,
            }

            if processing_method:
                filters["processing_method"] = processing_method.value

            # Query conversations using Supabase
            if self.supabase_client:
                response = await self.supabase_client.get_conversations_with_filters(
                    filters=filters,
                    limit=limit,
                    offset=offset,
                    order_by="processing_completed_at",
                )

                conversations = response.get("data", [])
                total_count = response.get("count", 0)
            else:
                # Fallback - return empty result
                conversations = []
                total_count = 0

            # Enhance conversations with approval context
            enhanced_conversations = []
            for conv in conversations:
                enhanced_conv = await self._enhance_conversation_for_approval(conv)
                enhanced_conversations.append(enhanced_conv)

            return {
                "conversations": enhanced_conversations,
                "total_count": total_count,
                "page_info": {
                    "limit": limit,
                    "offset": offset,
                    "has_next": offset + limit < total_count,
                },
            }

        except Exception as e:
            logger.error(f"Failed to get pending approvals: {e}")
            raise

    async def _enhance_conversation_for_approval(
        self, conversation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enhance conversation data with approval context"""
        enhanced = conversation.copy()

        # Add processing quality indicators
        processing_method = conversation.get("processing_method", "unknown")
        extraction_confidence = conversation.get("extraction_confidence", 0.0)

        # Determine review priority based on processing method and confidence
        if processing_method == ProcessingMethod.PDF_OCR.value:
            if extraction_confidence < 0.7:
                enhanced["review_priority"] = "high"
                enhanced["review_reason"] = (
                    "Low OCR confidence - manual review recommended"
                )
            elif extraction_confidence < 0.85:
                enhanced["review_priority"] = "medium"
                enhanced["review_reason"] = "Moderate OCR confidence"
            else:
                enhanced["review_priority"] = "low"
                enhanced["review_reason"] = "High OCR confidence"
        elif processing_method == ProcessingMethod.MANUAL_TEXT.value:
            enhanced["review_priority"] = "low"
            enhanced["review_reason"] = "Manually entered text"
        else:
            enhanced["review_priority"] = "medium"
            enhanced["review_reason"] = "Standard review required"

        # Add text statistics
        extracted_text = conversation.get("extracted_text", "")
        if extracted_text:
            enhanced["text_stats"] = {
                "character_count": len(extracted_text),
                "word_count": len(extracted_text.split()),
                "line_count": len(extracted_text.split("\\n")),
                "estimated_read_time_minutes": max(
                    1, len(extracted_text.split()) // 200
                ),
            }

        # Add approval metadata
        enhanced["approval_metadata"] = {
            "requires_review": True,
            "can_auto_approve": (
                extraction_confidence > 0.9 if extraction_confidence else False
            ),
            "processing_warnings": conversation.get("processing_warnings", []),
        }

        return enhanced

    async def process_approval_decision(
        self, decision: ApprovalDecision
    ) -> Dict[str, Any]:
        """
        Process a human approval decision

        Args:
            decision: The approval decision to process

        Returns:
            Dict with processing results
        """
        try:
            conversation_id = decision.conversation_id

            # Get current conversation
            if self.supabase_client:
                conversation = await self.supabase_client.get_conversation_by_id(
                    conversation_id
                )
            else:
                raise Exception("Supabase client not available")

            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Validate current status
            current_status = conversation.get("approval_status", "pending")
            if current_status != ApprovalStatus.PENDING.value:
                raise ValueError(
                    f"Conversation is in '{current_status}' status and cannot be processed"
                )

            # Process based on action
            result = await self._execute_approval_action(conversation, decision)

            # Log the decision
            await self._log_approval_decision(decision, result)

            return result

        except Exception as e:
            logger.error(f"Failed to process approval decision: {e}")
            raise

    async def _execute_approval_action(
        self, conversation: Dict[str, Any], decision: ApprovalDecision
    ) -> Dict[str, Any]:
        """Execute the specific approval action"""

        if decision.action == ApprovalAction.APPROVE:
            return await self._approve_text(conversation, decision)

        elif decision.action == ApprovalAction.REJECT:
            return await self._reject_text(conversation, decision)

        elif decision.action == ApprovalAction.EDIT_AND_APPROVE:
            return await self._edit_and_approve_text(conversation, decision)

        elif decision.action == ApprovalAction.REQUEST_REPROCESS:
            return await self._request_reprocess(conversation, decision)

        else:
            raise ValueError(f"Unknown approval action: {decision.action}")

    async def _approve_text(
        self, conversation: Dict[str, Any], decision: ApprovalDecision
    ) -> Dict[str, Any]:
        """Approve the extracted text as-is"""

        update_data = {
            "approval_status": ApprovalStatus.APPROVED.value,
            "approved_by": decision.reviewer_id,
            "approved_at": decision.timestamp.isoformat(),
            "updated_at": decision.timestamp.isoformat(),
        }

        if decision.notes:
            update_data["reviewer_notes"] = decision.notes

        # Update conversation
        if self.supabase_client:
            await self.supabase_client.update_conversation(
                conversation_id=conversation["id"], updates=update_data
            )

        return {
            "action": "approved",
            "conversation_id": conversation["id"],
            "approved_by": decision.reviewer_id,
            "approved_at": decision.timestamp.isoformat(),
            "message": "Text approved successfully",
        }

    async def _reject_text(
        self, conversation: Dict[str, Any], decision: ApprovalDecision
    ) -> Dict[str, Any]:
        """Reject the extracted text"""

        update_data = {
            "approval_status": ApprovalStatus.REJECTED.value,
            "approved_by": decision.reviewer_id,  # Track who rejected
            "rejected_at": decision.timestamp.isoformat(),
            "rejection_reason": decision.feedback
            or decision.notes
            or "Rejected during review",
            "updated_at": decision.timestamp.isoformat(),
        }

        # Update conversation
        if self.supabase_client:
            await self.supabase_client.update_conversation(
                conversation_id=conversation["id"], updates=update_data
            )

        return {
            "action": "rejected",
            "conversation_id": conversation["id"],
            "rejected_by": decision.reviewer_id,
            "rejected_at": decision.timestamp.isoformat(),
            "rejection_reason": update_data["rejection_reason"],
            "message": "Text rejected - conversation marked for revision",
        }

    async def _edit_and_approve_text(
        self, conversation: Dict[str, Any], decision: ApprovalDecision
    ) -> Dict[str, Any]:
        """Edit the text and approve the edited version"""

        if not decision.edited_text:
            raise ValueError("Edited text is required for edit_and_approve action")

        # Create backup of original text
        original_text = conversation.get("extracted_text", "")

        update_data = {
            "extracted_text": decision.edited_text,
            "approval_status": ApprovalStatus.APPROVED.value,
            "approved_by": decision.reviewer_id,
            "approved_at": decision.timestamp.isoformat(),
            "updated_at": decision.timestamp.isoformat(),
            "original_extracted_text_backup": original_text,  # Backup original
            "manual_edits_applied": True,
        }

        if decision.notes:
            update_data["reviewer_notes"] = decision.notes

        # Update conversation
        if self.supabase_client:
            await self.supabase_client.update_conversation(
                conversation_id=conversation["id"], updates=update_data
            )

        return {
            "action": "edited_and_approved",
            "conversation_id": conversation["id"],
            "approved_by": decision.reviewer_id,
            "approved_at": decision.timestamp.isoformat(),
            "edits_applied": True,
            "original_text_backed_up": True,
            "message": "Text edited and approved successfully",
        }

    async def _request_reprocess(
        self, conversation: Dict[str, Any], decision: ApprovalDecision
    ) -> Dict[str, Any]:
        """Request reprocessing of the document"""

        update_data = {
            "processing_status": ProcessingStatus.PENDING.value,
            "approval_status": ApprovalStatus.PENDING.value,
            "reprocess_requested_by": decision.reviewer_id,
            "reprocess_requested_at": decision.timestamp.isoformat(),
            "reprocess_reason": decision.feedback
            or decision.notes
            or "Reprocessing requested",
            "updated_at": decision.timestamp.isoformat(),
        }

        # Update conversation
        if self.supabase_client:
            await self.supabase_client.update_conversation(
                conversation_id=conversation["id"], updates=update_data
            )

        return {
            "action": "reprocess_requested",
            "conversation_id": conversation["id"],
            "requested_by": decision.reviewer_id,
            "requested_at": decision.timestamp.isoformat(),
            "reason": update_data["reprocess_reason"],
            "message": "Reprocessing requested - conversation will be reprocessed",
        }

    async def _log_approval_decision(
        self, decision: ApprovalDecision, result: Dict[str, Any]
    ) -> None:
        """Log the approval decision for audit trail"""

        log_entry = {
            "conversation_id": decision.conversation_id,
            "action": decision.action.value,
            "reviewer_id": decision.reviewer_id,
            "timestamp": decision.timestamp.isoformat(),
            "notes": decision.notes,
            "result": result.get("action"),
            "success": True,
        }

        logger.info(f"Approval decision logged: {log_entry}")

        # Could also store in database audit table if needed
        # await self.supabase_client.log_approval_decision(log_entry)

    async def assess_text_quality(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> QualityMetrics:
        """Assess the quality of extracted text"""
        issues = []
        suggestions = []

        # Basic text validation
        if not text or len(text.strip()) < MIN_TEXT_LENGTH:
            issues.append("Text is too short")
            suggestions.append("Consider reprocessing with higher quality settings")
            readability_score = 0.0
        elif len(text) > MAX_TEXT_LENGTH:
            issues.append("Text exceeds maximum length")
            suggestions.append("Consider splitting into multiple documents")
            readability_score = 0.5
        else:
            readability_score = 0.8

        # Check for common OCR issues
        ocr_issues = self._detect_ocr_issues(text)
        if ocr_issues:
            issues.extend(ocr_issues)
            readability_score *= 0.8
            suggestions.append("Manual review recommended for OCR accuracy")

        # Check formatting
        formatting_score = self._assess_formatting(text)

        # Check language quality
        language_quality = self._assess_language_quality(text)

        # Calculate completeness
        completeness_score = min(
            len(text.split()) / 100, 1.0
        )  # Assume 100 words minimum

        # Overall score
        overall_score = (
            readability_score * 0.3
            + completeness_score * 0.2
            + formatting_score * 0.2
            + language_quality * 0.3
        )

        return QualityMetrics(
            readability_score=readability_score,
            completeness_score=completeness_score,
            formatting_score=formatting_score,
            language_quality=language_quality,
            overall_score=overall_score,
            issues=issues,
            suggestions=suggestions,
        )

    def _detect_ocr_issues(self, text: str) -> List[str]:
        """Detect common OCR issues in text"""
        issues = []

        # Check for excessive special characters (OCR artifacts)
        special_char_ratio = len(re.findall(r"[^\w\s]", text)) / max(len(text), 1)
        if special_char_ratio > 0.3:
            issues.append("High ratio of special characters detected")

        # Check for repeated characters (OCR glitches)
        if re.search(r"(.)\1{4,}", text):
            issues.append("Repeated character sequences detected")

        # Check for mixed case issues
        if re.search(r"\b[a-z]+[A-Z]+[a-z]+\b", text):
            issues.append("Unusual mixed case patterns detected")

        # Check for common OCR substitutions
        ocr_patterns = [
            (r"\brn\b", 'Possible "m" misread as "rn"'),
            (r"\bcl\b", 'Possible "d" misread as "cl"'),
            (r"\b0\b", 'Possible "O" misread as "0"'),
            (r"\b1\b", 'Possible "I" or "l" misread as "1"'),
        ]

        for pattern, issue in ocr_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                issues.append(issue)

        return issues

    def _assess_formatting(self, text: str) -> float:
        """Assess text formatting quality"""
        score = 1.0

        # Check for proper paragraph breaks
        if "\n\n" not in text and len(text) > 500:
            score *= 0.8

        # Check for excessive whitespace
        if "   " in text or "\n\n\n" in text:
            score *= 0.9

        # Check for balanced quotes and brackets
        for open_char, close_char in [("(", ")"), ("[", "]"), ("{", "}"), ('"', '"')]:
            if text.count(open_char) != text.count(close_char):
                score *= 0.95

        return max(score, 0.3)

    def _assess_language_quality(self, text: str) -> float:
        """Assess language quality (simplified)"""
        # In production, use a proper NLP library for language detection and quality assessment
        score = 1.0

        # Check for very short words (possible OCR errors)
        words = text.split()
        if words:
            avg_word_length = sum(len(w) for w in words) / len(words)
            if avg_word_length < 3:
                score *= 0.7
            elif avg_word_length > 15:
                score *= 0.8

        # Check for sentence structure (simplified)
        sentences = re.split(r"[.!?]+", text)
        valid_sentences = [s for s in sentences if len(s.split()) > 3]
        if len(valid_sentences) < len(sentences) * 0.5:
            score *= 0.8

        return max(score, 0.3)

    async def process_batch_approval(
        self,
        conversation_ids: List[int],
        action: ApprovalAction,
        reviewer_id: str,
        reviewer_role: ReviewerRole,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process batch approval decision"""
        # Verify batch size
        if len(conversation_ids) > MAX_BATCH_SIZE:
            raise ValueError(
                f"Batch size ({len(conversation_ids)}) exceeds maximum ({MAX_BATCH_SIZE})"
            )

        # Verify permissions
        has_permission, error_msg = await self.verify_reviewer_permission(
            reviewer_id, action
        )
        if not has_permission:
            raise PermissionError(error_msg)

        successful: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        results: Dict[str, Any] = {
            "successful": successful,
            "failed": failed,
            "total": len(conversation_ids),
        }

        # Process each conversation
        for conv_id in conversation_ids:
            try:
                decision = ApprovalDecision(
                    conversation_id=conv_id,
                    action=(
                        ApprovalAction.APPROVE
                        if action == ApprovalAction.BATCH_APPROVE
                        else ApprovalAction.REJECT
                    ),
                    reviewer_id=reviewer_id,
                    reviewer_role=reviewer_role,
                    notes=notes or f"Batch {action.value}",
                )

                result = await self.process_approval_decision(decision)
                successful.append({"conversation_id": conv_id, "result": result})

            except Exception as e:
                logger.error(f"Batch processing failed for conversation {conv_id}: {e}")
                failed.append({"conversation_id": conv_id, "error": str(e)})

        # Send batch notification
        if self.notification_service:
            await self.notification_service.send_batch_approval_notification(
                reviewer_id=reviewer_id,
                action=action,
                success_count=len(successful),
                failed_count=len(failed),
            )

        return results

    async def auto_approve_high_confidence(self) -> Dict[str, Any]:
        """Automatically approve high-confidence extractions"""
        # Get high-confidence pending approvals
        filters = {
            "processing_status": ProcessingStatus.COMPLETED.value,
            "approval_status": ApprovalStatus.PENDING.value,
            "extraction_confidence__gte": AUTO_APPROVE_CONFIDENCE,
        }

        if self.supabase_client:
            response = await self.supabase_client.get_conversations_with_filters(
                filters=filters, limit=100
            )

            conversations = response.get("data", [])
            results = {"auto_approved": 0, "skipped": 0, "errors": 0}

            for conv in conversations:
                try:
                    # Additional quality check
                    quality = await self.assess_text_quality(
                        conv.get("extracted_text", "")
                    )

                    if quality.overall_score >= 0.8 and not quality.issues:
                        # Auto-approve
                        decision = ApprovalDecision(
                            conversation_id=conv["id"],
                            action=ApprovalAction.AUTO_APPROVE,
                            reviewer_id="system",
                            reviewer_role=ReviewerRole.ADMIN,
                            notes="Auto-approved due to high confidence and quality",
                            quality_score=quality.overall_score,
                            confidence_score=conv.get("extraction_confidence", 0),
                        )

                        await self.process_approval_decision(decision)
                        results["auto_approved"] += 1
                        self.metrics["auto_approvals"] += 1
                    else:
                        results["skipped"] += 1
                        logger.info(
                            f"Skipped auto-approval for conversation {conv['id']}: quality issues"
                        )

                except Exception as e:
                    logger.error(
                        f"Auto-approval failed for conversation {conv['id']}: {e}"
                    )
                    results["errors"] += 1

            return results

        return {"error": "Supabase client not available"}

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def send_webhook_notification(self, event_type: str, data: Dict[str, Any]):
        """Send webhook notification for approval events"""
        if not self.webhook_enabled or not self.webhook_url:
            return

        payload = {
            "event": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status >= 400:
                        logger.error(f"Webhook failed with status {response.status}")
                    else:
                        logger.info(
                            f"Webhook sent successfully for event: {event_type}"
                        )
            except Exception as e:
                logger.error(f"Webhook notification failed: {e}")
                raise

    def get_workflow_metrics(self) -> Dict[str, Any]:
        """Get current workflow metrics"""
        total_decisions = max(self.metrics["decisions_processed"], 1)

        return {
            "total_decisions": self.metrics["decisions_processed"],
            "auto_approval_rate": self.metrics["auto_approvals"] / total_decisions,
            "manual_approval_rate": self.metrics["manual_approvals"] / total_decisions,
            "rejection_rate": self.metrics["rejections"] / total_decisions,
            "escalation_rate": self.metrics["escalations"] / total_decisions,
            "average_review_time_seconds": self.metrics["average_review_time"],
            "cache_stats": {
                "quality_cache_size": len(self._quality_cache),
                "role_cache_size": len(self._user_role_cache),
            },
        }

    async def cleanup_expired_approvals(self) -> int:
        """Clean up expired pending approvals"""
        cutoff_time = datetime.utcnow() - timedelta(hours=APPROVAL_TIMEOUT_HOURS)

        if self.supabase_client:
            # Mark expired approvals as timed out
            result = await self.supabase_client.update_expired_approvals(
                cutoff_time=cutoff_time.isoformat(),
                new_status=ApprovalStatus.REJECTED.value,
                rejection_reason="Approval timeout exceeded",
            )

            count = result.get("affected_rows", 0)
            logger.info(f"Cleaned up {count} expired approvals")
            return count

        return 0

    async def get_approval_statistics(self) -> Dict[str, Any]:
        """Get approval workflow statistics"""

        try:
            if not self.supabase_client:
                return {"error": "Supabase client not available"}

            # Get overall approval stats
            stats = await self.supabase_client.get_approval_workflow_stats()

            # Enhanced stats for text approval workflow
            enhanced_stats = {
                "total_conversations": stats.get("total_conversations", 0),
                "pending_approval": stats.get("pending_approval", 0),
                "approved": stats.get("approved", 0),
                "rejected": stats.get("rejected", 0),
                "processing_method_breakdown": {
                    "pdf_ocr": 0,  # Would need specific query
                    "manual_text": 0,
                    "text_paste": 0,
                },
                "quality_indicators": {
                    "high_confidence_count": 0,  # confidence > 0.85
                    "medium_confidence_count": 0,  # 0.7 <= confidence <= 0.85
                    "low_confidence_count": 0,  # confidence < 0.7
                    "manual_edits_count": 0,  # Number with manual edits applied
                },
            }

            return enhanced_stats

        except Exception as e:
            logger.error(f"Failed to get approval statistics: {e}")
            return {"error": str(e)}
