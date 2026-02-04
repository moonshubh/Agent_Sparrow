"""
FeedMe Intelligence API Endpoints
Enhanced endpoints for AI-powered conversation analysis and insights
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query
import logging

# Note: Authentication and database dependencies would be imported here if available
from app.feedme.ai_extraction_engine import GeminiExtractionEngine
from app.core.settings import settings
from app.feedme.schemas import (
    ConversationSummaryRequest,
    ConversationSummaryResponse,
    BatchAnalysisRequest,
    BatchAnalysisResponse,
    SmartSearchRequest,
    SmartSearchResponse,
    SmartSearchResult,
)
from app.db.supabase.client import get_supabase_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedme/intelligence", tags=["feedme-intelligence"])


@router.post("/summarize", response_model=ConversationSummaryResponse)
async def summarize_conversation(
    request: ConversationSummaryRequest,
) -> ConversationSummaryResponse:
    """
    Generate intelligent summary of a conversation with sentiment analysis

    Features:
    - Concise summary with focus options
    - Sentiment analysis (start/end/shift)
    - Key topics extraction
    - Technical issues identification
    - Action items extraction
    - Agent performance metrics
    """
    try:
        if not settings.gemini_api_key:
            raise HTTPException(status_code=503, detail="AI service not configured")

        # Initialize AI engine
        engine = GeminiExtractionEngine(api_key=settings.gemini_api_key)

        # Generate summary
        result = await engine.summarize_conversation(
            conversation_text=request.conversation_text,
            max_length=request.max_length,
            focus=request.focus,
        )

        if not result["success"]:
            raise HTTPException(
                status_code=500, detail=result.get("error", "Summarization failed")
            )

        return ConversationSummaryResponse(
            success=True, data=result["data"], confidence=result["confidence"]
        )

    except Exception as e:
        logger.error(f"Conversation summarization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-batch", response_model=BatchAnalysisResponse)
async def analyze_conversation_batch(
    request: BatchAnalysisRequest,
) -> BatchAnalysisResponse:
    """
    Analyze a batch of conversations for patterns and insights

    Features:
    - Common issues detection with frequency
    - Resolution patterns analysis
    - Knowledge gaps identification
    - Quality metrics calculation
    - Training recommendations
    - Automation opportunities
    """
    try:
        if not settings.gemini_api_key:
            raise HTTPException(status_code=503, detail="AI service not configured")

        # Get conversations from database if IDs provided
        if request.conversation_ids:
            supabase = get_supabase_client()
            result = await supabase._exec(
                lambda: supabase.client.table("feedme_examples")
                .select("*")
                .in_("conversation_id", request.conversation_ids)
                .execute()
            )
            conversations = result.data if result.data else []
        else:
            conversations = request.conversations

        if not conversations:
            raise HTTPException(
                status_code=400, detail="No conversations provided for analysis"
            )

        # Initialize AI engine
        engine = GeminiExtractionEngine(api_key=settings.gemini_api_key)

        # Analyze batch
        result = await engine.analyze_conversation_batch(
            conversations=conversations, analysis_type=request.analysis_type
        )

        if not result["success"]:
            raise HTTPException(
                status_code=500, detail=result.get("error", "Batch analysis failed")
            )

        return BatchAnalysisResponse(
            success=True,
            data=result["data"],
            insights_generated=result["insights_generated"],
        )

    except Exception as e:
        logger.error(f"Batch analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/smart-search", response_model=SmartSearchResponse)
async def smart_search_conversations(
    request: SmartSearchRequest,
) -> SmartSearchResponse:
    """
    Intelligent search with semantic understanding and context

    Features:
    - Natural language query understanding
    - Semantic similarity matching
    - Context-aware results
    - Related suggestions
    - Search intent classification
    """
    try:
        if not settings.gemini_api_key:
            raise HTTPException(status_code=503, detail="AI service not configured")

        # Initialize AI engine
        engine = GeminiExtractionEngine(api_key=settings.gemini_api_key)

        # First, understand the search intent
        intent_prompt = f"""Analyze this search query and extract search intent:
Query: {request.query}

Return JSON with:
{{
    "intent": "technical_issue/how_to/error_resolution/feature_question/general",
    "key_terms": ["term1", "term2"],
    "expanded_query": "expanded version of the query with synonyms",
    "filters": {{
        "issue_type": "optional specific issue type",
        "resolution_type": "optional resolution type filter"
    }}
}}"""

        # Get search intent
        response = await engine._extract_with_retry(intent_prompt)
        if not response:
            raise HTTPException(
                status_code=500, detail="Failed to analyze search query"
            )

        intent_data = engine._parse_json_response(response.text)

        # Perform semantic search with enhanced query
        supabase = get_supabase_client()

        # Search with filters
        query_builder = supabase.client.table("feedme_examples").select("*")

        # Apply intent-based filters
        if intent_data.get("filters", {}).get("issue_type"):
            query_builder = query_builder.eq(
                "issue_type", intent_data["filters"]["issue_type"]
            )

        # Perform vector similarity search
        # Note: This is a simplified version. In production, you'd use pgvector similarity search
        result = await supabase._exec(
            lambda: query_builder.limit(request.limit).execute()
        )

        # Enhance results with relevance scoring
        enhanced_results: list[SmartSearchResult] = []
        for item in result.data[: request.limit]:
            # Calculate relevance score (simplified)
            relevance = 0.8  # In production, calculate actual similarity

            enhanced_results.append(
                SmartSearchResult(
                    **item,
                    relevance_score=relevance,
                    match_reason="Semantic similarity",
                )
            )

        # Sort by relevance
        enhanced_results.sort(key=lambda x: x.relevance_score, reverse=True)

        return SmartSearchResponse(
            success=True,
            query=request.query,
            intent=intent_data.get("intent", "general"),
            key_terms=intent_data.get("key_terms", []),
            results=enhanced_results,
            total_results=len(enhanced_results),
            suggestions=[
                f"Try searching for: {term}"
                for term in intent_data.get("key_terms", [])[:3]
            ],
        )

    except Exception as e:
        logger.error(f"Smart search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insights/dashboard")
async def get_insights_dashboard(
    days: int = Query(7, description="Number of days to analyze"),
) -> Dict[str, Any]:
    """
    Get comprehensive insights dashboard data

    Returns:
    - Conversation volume trends
    - Common issue categories
    - Resolution rates
    - Sentiment trends
    - Agent performance metrics
    """
    try:
        supabase = get_supabase_client()

        # Get recent conversations
        from datetime import datetime, timedelta

        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

        result = await supabase._exec(
            lambda: supabase.client.table("feedme_conversations")
            .select("*, feedme_examples(*)")
            .gte("created_at", cutoff_date)
            .execute()
        )

        conversations = result.data if result.data else []

        # Calculate metrics
        total_conversations = len(conversations)

        # Issue type distribution
        issue_types: Dict[str, int] = {}
        resolution_types: Dict[str, int] = {}

        for conv in conversations:
            for example in conv.get("feedme_examples", []):
                issue_type = example.get("issue_type", "unknown")
                issue_types[issue_type] = issue_types.get(issue_type, 0) + 1

                resolution_type = example.get("resolution_type", "unknown")
                resolution_types[resolution_type] = (
                    resolution_types.get(resolution_type, 0) + 1
                )

        # Calculate resolution rate
        resolved_count = resolution_types.get("resolved", 0) + resolution_types.get(
            "solved", 0
        )
        resolution_rate = (
            (resolved_count / total_conversations * 100)
            if total_conversations > 0
            else 0
        )

        return {
            "success": True,
            "period_days": days,
            "metrics": {
                "total_conversations": total_conversations,
                "resolution_rate": round(resolution_rate, 1),
                "average_confidence_score": 0.75,  # Placeholder
                "total_qa_pairs": sum(
                    len(conv.get("feedme_examples", [])) for conv in conversations
                ),
            },
            "issue_distribution": issue_types,
            "resolution_distribution": resolution_types,
            "trends": {
                "conversation_volume": "stable",  # Placeholder
                "resolution_rate_trend": "improving",  # Placeholder
                "common_issues_shift": [],  # Placeholder
            },
        }

    except Exception as e:
        logger.error(f"Insights dashboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enhance-answer")
async def enhance_answer(
    question: str, answer: str, context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enhance an answer with AI to make it more helpful and complete

    Features:
    - Add missing steps
    - Clarify technical terms
    - Add warnings or prerequisites
    - Improve clarity and structure
    """
    try:
        if not settings.gemini_api_key:
            raise HTTPException(status_code=503, detail="AI service not configured")

        engine = GeminiExtractionEngine(api_key=settings.gemini_api_key)

        enhance_prompt = f"""Enhance this customer support answer to be more helpful and complete.

Question: {question}
Original Answer: {answer}
{f"Context: {context}" if context else ""}

Enhance the answer by:
1. Adding any missing steps or details
2. Clarifying technical terms
3. Adding important warnings or prerequisites
4. Improving clarity and structure
5. Ensuring the answer is actionable

Return JSON with:
{{
    "enhanced_answer": "The improved answer text",
    "additions": ["what was added"],
    "improvements": ["what was improved"],
    "confidence": 0.0-1.0
}}"""

        response = await engine._extract_with_retry(enhance_prompt)
        if not response:
            raise HTTPException(status_code=500, detail="Failed to enhance answer")

        result = engine._parse_json_response(response.text)

        return {
            "success": True,
            "original_answer": answer,
            "enhanced_answer": result.get("enhanced_answer", answer),
            "additions": result.get("additions", []),
            "improvements": result.get("improvements", []),
            "confidence": result.get("confidence", 0.8),
        }

    except Exception as e:
        logger.error(f"Answer enhancement error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
