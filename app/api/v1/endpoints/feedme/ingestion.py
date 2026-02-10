"""
FeedMe Ingestion Endpoints

Handles file upload and transcript processing initiation.
"""

import logging
import os
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import (
    APIRouter,
    HTTPException,
    UploadFile,
    File,
    Form,
    BackgroundTasks,
    Request,
    Response,
    Depends,
    status,
)

from app.core.settings import settings
from app.core.security import TokenPayload
from app.feedme.security import (
    SecureTitleModel,
    FileUploadValidator,
    SecurityValidator,
    SecurityAuditLogger,
    limiter,
    validate_request_size,
)
from app.feedme.schemas import (
    ConversationCreate,
    ConversationUploadResponse,
    ProcessingStatus,
    ProcessingStage,
    ProcessingMethod,
)

from .helpers import (
    create_conversation_in_db,
    get_feedme_supabase_client,
    record_feedme_action_audit,
    update_conversation_status,
)
from .auth import require_feedme_admin

logger = logging.getLogger(__name__)
audit_logger = SecurityAuditLogger()

router = APIRouter(tags=["FeedMe"])


@router.post(
    "/conversations/upload", response_model=ConversationUploadResponse, status_code=202
)
@limiter.limit("10/minute")
async def upload_transcript(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    title: str = Form(..., description="Conversation title"),
    uploaded_by: Optional[str] = Form(
        None, description="User uploading the transcript"
    ),
    auto_process: bool = Form(
        True, description="Whether to automatically process the transcript"
    ),
    transcript_file: Optional[UploadFile] = File(
        None, description="PDF file to upload"
    ),
    current_user: TokenPayload = Depends(require_feedme_admin),
):
    """
    Uploads a customer support transcript for ingestion.

    Accepts a PDF file upload. Creates a conversation record and optionally
    schedules it for background processing.

    Returns:
        ConversationUploadResponse: The created conversation status.

    Raises:
        HTTPException: If the service is disabled, input is invalid, or operations fail.
    """

    if not settings.feedme_enabled:
        raise HTTPException(
            status_code=503, detail="FeedMe service is currently disabled"
        )

    client_ip = request.client.host if request.client else "unknown"
    await validate_request_size(request)

    # Validate and sanitize title
    try:
        validated_title = SecureTitleModel(title=title)
        title = validated_title.title
    except ValueError as e:
        audit_logger.log_validation_failure(
            "title_validation", title[:100], str(e), client_ip
        )
        raise HTTPException(status_code=400, detail=str(e))

    # Validate input – PDF file is required
    if not transcript_file:
        raise HTTPException(status_code=400, detail="A PDF file is required")

    if not transcript_file.filename:
        audit_logger.log_validation_failure(
            "file_upload",
            "missing filename",
            "Filename is required",
            client_ip,
        )
        raise HTTPException(status_code=400, detail="Filename is required")

    filename = transcript_file.filename
    content_type = transcript_file.content_type

    # Read file content once for validation + duplicate hashing
    file_content = await transcript_file.read()

    # Validate file using security validator
    is_valid, error_msg = FileUploadValidator.validate_file(
        filename=filename,
        file_size=len(file_content),
        mime_type=content_type,
        content=file_content,
    )

    if not is_valid:
        message = error_msg or "File validation failed"
        audit_logger.log_validation_failure("file_upload", filename, message, client_ip)
        raise HTTPException(status_code=400, detail=message)

    original_filename = SecurityValidator.sanitize_filename(filename)
    upload_sha256 = hashlib.sha256(file_content).hexdigest()

    # Validate file size
    if len(file_content) > settings.feedme_max_file_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds maximum allowed size of {settings.feedme_max_file_size_mb}MB",
        )

    # Validate content type
    allowed_content_types = ["application/pdf"]
    if content_type and content_type not in allowed_content_types:
        logger.warning(f"Unexpected content type {content_type}")
        raise HTTPException(status_code=400, detail="Invalid file content type")

    # Check file extension
    filename_lower = filename.lower()
    is_pdf_file = filename_lower.endswith(".pdf") or (
        content_type and content_type == "application/pdf"
    )

    file_extension = os.path.splitext(filename_lower)[1]

    if is_pdf_file and not settings.feedme_pdf_enabled:
        raise HTTPException(
            status_code=400,
            detail="PDF file uploads are not enabled. Please contact your administrator.",
        )

    if file_extension and file_extension not in [".pdf"]:
        raise HTTPException(status_code=400, detail="Invalid file extension")

    # Process file content
    try:
        content_bytes = file_content
        # Note: original_filename already sanitized above

        if not is_pdf_file:
            raise HTTPException(
                status_code=400, detail="Only PDF uploads are supported"
            )

        final_content = base64.b64encode(content_bytes).decode("utf-8")
        mime_type = "application/pdf"
        file_format = "pdf"

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing file upload: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing uploaded file")

    # Validate content length
    if len(final_content.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="Transcript content must be at least 10 characters long",
        )

    initial_method = ProcessingMethod.PDF_AI
    uploaded_by = uploaded_by or current_user.sub

    # Duplicate detection window: 30 days by content hash.
    client = get_feedme_supabase_client()
    if client is None:
        raise HTTPException(
            status_code=503, detail="FeedMe service is temporarily unavailable."
        )
    duplicate_window_start = (
        datetime.now(timezone.utc) - timedelta(days=30)
    ).isoformat()
    duplicate_response = await client._exec(
        lambda: client.client.table("feedme_conversations")
        .select("id,processing_status,created_at")
        .eq("upload_sha256", upload_sha256)
        .gte("created_at", duplicate_window_start)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if duplicate_response.data:
        duplicate = duplicate_response.data[0]
        duplicate_id = int(duplicate["id"])
        status_raw = str(duplicate.get("processing_status") or "pending")
        processing_status = (
            ProcessingStatus(status_raw)
            if status_raw in {s.value for s in ProcessingStatus}
            else ProcessingStatus.PENDING
        )
        await record_feedme_action_audit(
            action="upload_duplicate_detected",
            actor_id=current_user.sub,
            conversation_id=duplicate_id,
            after_state={
                "duplicate_conversation_id": duplicate_id,
                "upload_sha256": upload_sha256,
                "duplicate_created_at": duplicate.get("created_at"),
            },
        )
        response.status_code = status.HTTP_200_OK
        return ConversationUploadResponse(
            message="Duplicate PDF detected. Reusing existing conversation.",
            conversation_id=duplicate_id,
            processing_status=processing_status,
            duplicate=True,
            duplicate_conversation_id=duplicate_id,
            upload_sha256=upload_sha256,
        )

    conversation_data = ConversationCreate(
        title=title,
        original_filename=original_filename,
        raw_transcript=final_content,
        extracted_text=None,
        uploaded_by=uploaded_by,
        approved_by=None,
        approved_at=None,
        metadata={"auto_process": auto_process, "file_format": file_format},
        mime_type=mime_type,
        pages=None,
        processing_method=initial_method,
        extraction_confidence=None,
        pdf_metadata=None,
    )

    try:
        conversation = await create_conversation_in_db(
            conversation_data,
            upload_sha256=upload_sha256,
            os_category="uncategorized",
        )
        await record_feedme_action_audit(
            action="upload_conversation",
            actor_id=current_user.sub,
            conversation_id=conversation.id,
            after_state={
                "title": conversation.title,
                "upload_sha256": upload_sha256,
                "original_filename": original_filename,
            },
        )

        if auto_process:
            background_tasks.add_task(
                process_uploaded_transcript,
                conversation.id,
                conversation.uploaded_by,
            )

        return ConversationUploadResponse(
            message="Conversation upload accepted for processing.",
            conversation_id=conversation.id,
            processing_status=conversation.processing_status,
            duplicate=False,
            upload_sha256=upload_sha256,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")


async def process_uploaded_transcript(conversation_id: int, processed_by: str):
    """Background task to process a newly uploaded transcript."""
    try:
        from app.feedme.tasks import process_transcript

        logger.info(
            f"Starting background processing for conversation {conversation_id}"
        )

        await update_conversation_status(
            conversation_id,
            ProcessingStatus.PENDING,
            stage=ProcessingStage.QUEUED,
            progress=0,
            message="Queued for processing",
        )

        task = process_transcript.delay(conversation_id, processed_by)
        logger.info(
            f"Scheduled Celery task {task.id} for conversation {conversation_id}"
        )

    except Exception as e:
        logger.error(
            f"Background processing scheduling failed for conversation {conversation_id}: {e}"
        )
        await update_conversation_status(
            conversation_id,
            ProcessingStatus.FAILED,
            error_message=str(e),
            stage=ProcessingStage.FAILED,
            progress=0,
            message="Scheduling failed",
        )
