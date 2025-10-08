"""
Agent Sparrow - Emotional Intelligence Templates

This module provides sophisticated emotion detection and response templates
for adapting communication style based on customer emotional state.
"""

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import re


class EmotionalState(Enum):
    """Customer emotional states that Agent Sparrow can detect and respond to"""
    FRUSTRATED = "frustrated"
    CONFUSED = "confused" 
    ANXIOUS = "anxious"
    PROFESSIONAL = "professional"
    EXCITED = "excited"
    URGENT = "urgent"
    DISAPPOINTED = "disappointed"
    NEUTRAL = "neutral"


@dataclass
class EmotionDetectionResult:
    """Result of emotion detection analysis"""
    primary_emotion: EmotionalState
    confidence_score: float  # 0.0 to 1.0
    detected_indicators: List[str]
    secondary_emotions: List[EmotionalState]


class EmotionTemplates:
    """
    Sophisticated emotional intelligence system for Agent Sparrow
    
    Provides emotion detection, empathy templates, and response strategies
    to adapt communication style based on customer emotional state.
    """
    
    # Emotion detection patterns
    EMOTION_PATTERNS = {
        EmotionalState.FRUSTRATED: {
            "keywords": [
                "stupid", "broken", "useless", "terrible", "awful", "horrible",
                "worst", "hate", "frustrated", "annoying", "ridiculous", "pathetic"
            ],
            "patterns": [
                r"(?i)this is (so |really )?stupid",
                r"(?i)(completely|totally) broken",
                r"(?i)doesn't work at all",
                r"(?i)waste of (time|money)",
                r"!!{2,}",  # Multiple exclamation marks
                r"[A-Z]{10,}",  # Long caps sequences
            ],
            "intensity_multipliers": {
                "!!": 1.2,
                "!!!": 1.5, 
                "CAPS": 1.3,
                "profanity": 1.8
            }
        },
        
        EmotionalState.CONFUSED: {
            "keywords": [
                "confused", "don't understand", "don't know", "lost", "unclear",
                "how do", "what is", "where is", "help me understand", "not sure"
            ],
            "patterns": [
                r"(?i)i don't (understand|know|get)",
                r"(?i)how do i",
                r"(?i)what (is|does|should)",
                r"(?i)(where|how) can i",
                r"(?i)confused about",
                r"(?i)not sure (how|what|where)"
            ]
        },
        
        EmotionalState.ANXIOUS: {
            "keywords": [
                "urgent", "important", "worried", "concerned", "deadline", "asap",
                "emergency", "critical", "losing", "lost", "missing", "scared"
            ],
            "patterns": [
                r"(?i)(urgent|emergency|critical|important)",
                r"(?i)need (this|it) (today|now|asap)",
                r"(?i)(worried|concerned) about",
                r"(?i)(losing|lost) (emails|data)",
                r"(?i)deadline",
                r"(?i)can't afford to"
            ]
        },
        
        EmotionalState.PROFESSIONAL: {
            "keywords": [
                "regarding", "concerning", "kindly", "appreciate", "thank you",
                "please", "could you", "would you", "assistance", "support"
            ],
            "patterns": [
                r"(?i)thank you for",
                r"(?i)i would appreciate",
                r"(?i)could you please",
                r"(?i)regarding the",
                r"(?i)i am writing to",
                r"(?i)looking forward to"
            ]
        },
        
        EmotionalState.EXCITED: {
            "keywords": [
                "awesome", "amazing", "great", "excellent", "fantastic", "love",
                "excited", "perfect", "wonderful", "brilliant"
            ],
            "patterns": [
                r"(?i)(this is|you're) (awesome|amazing|great)",
                r"(?i)love (this|it|mailbird)",
                r"(?i)(so|really) excited",
                r"(?i)perfect(ly)?",
                r"(?i)exactly what i needed"
            ]
        },
        
        EmotionalState.URGENT: {
            "keywords": [
                "urgent", "asap", "immediately", "now", "emergency", "critical",
                "deadline", "today", "quickly", "fast"
            ],
            "patterns": [
                r"(?i)(urgent|emergency|critical)",
                r"(?i)need (this|it) (now|today|asap|immediately)",
                r"(?i)as soon as possible",
                r"(?i)right away",
                r"(?i)time sensitive"
            ]
        },
        
        EmotionalState.DISAPPOINTED: {
            "keywords": [
                "disappointed", "expected", "supposed to", "should", "promised",
                "let down", "unhappy", "unsatisfied"
            ],
            "patterns": [
                r"(?i)(disappointed|let down)",
                r"(?i)expected (it|this) to",
                r"(?i)(supposed|should) to work",
                r"(?i)was promised",
                r"(?i)not what i expected"
            ]
        }
    }
    
    # Empathy response templates by emotion
    EMPATHY_TEMPLATES = {
        EmotionalState.FRUSTRATED: [
            "I completely understand how frustrating it must be when {issue}. This definitely isn't the experience we want you to have with Mailbird, and I sincerely apologize for the inconvenience. Let me help you resolve this right away...",
            "I can really hear your frustration about {issue}, and I don't blame you one bit. Email is such an essential part of your workflow, and when it's not working properly, it affects everything. Let's get this sorted out for you immediately...",
            "Your frustration is completely valid - {issue} should absolutely work better than this. I'm genuinely sorry this is causing you stress. I'm here to make this right and get you back to productive email management..."
        ],
        
        EmotionalState.CONFUSED: [
            "No worries at all - {topic} can be tricky! I'm here to guide you through this step by step. Let's start with...",
            "I totally understand the confusion around {topic}. Email client setup can involve a lot of moving parts, and it's completely normal to need guidance. Let me walk you through this clearly...",
            "Don't worry about not understanding {topic} immediately - these systems can be complex! I'll explain everything in simple terms and make sure you're comfortable with each step..."
        ],
        
        EmotionalState.ANXIOUS: [
            "I want to reassure you right away that {concern}. Your emails and data are safe, and we can definitely resolve this situation. Here's exactly what we'll do...",
            "I understand how concerning {issue} must be, especially when you're dealing with important emails. Let me put your mind at ease - we have reliable solutions for this, and I'll guide you through everything...",
            "I can sense your urgency about {concern}, and I want to address that worry immediately. Mailbird is designed with data safety in mind, and we'll get this resolved quickly..."
        ],
        
        EmotionalState.PROFESSIONAL: [
            "Thank you for reaching out about {issue}. I'll provide you with comprehensive assistance to resolve this efficiently...",
            "I appreciate you taking the time to contact us regarding {topic}. Let me provide you with the detailed information you need...",
            "Thank you for your professional inquiry about {issue}. I'm happy to provide thorough guidance on this matter..."
        ],
        
        EmotionalState.EXCITED: [
            "I love your enthusiasm about {topic}! Mailbird really shines when it comes to {feature}, and I'm excited to help you get the most out of it...",
            "It's wonderful to hear your positive experience with {feature}! Let me share some additional insights that will make your Mailbird experience even better...",
            "Your excitement about {topic} is contagious! There are some fantastic features I think you'll love even more. Let me show you..."
        ],
        
        EmotionalState.URGENT: [
            "I understand this is time-sensitive for you. Let me provide you with the fastest path to resolution for {issue}...",
            "Given the urgency of {issue}, I'll give you both a quick workaround and the complete solution. Here's what you can do right now...",
            "I recognize you need this resolved quickly. Let me prioritize the most effective solution for {issue} that will get you back up and running immediately..."
        ],
        
        EmotionalState.DISAPPOINTED: [
            "I'm genuinely sorry that {issue} hasn't met your expectations. That's not the Mailbird experience we want you to have, and I'd like to make this right...",
            "I understand your disappointment about {issue}. We clearly haven't delivered the experience you were hoping for, and I want to address that directly...",
            "Your disappointment is completely understandable given {issue}. Let me work to restore your confidence in Mailbird by getting this properly resolved..."
        ],
        
        EmotionalState.NEUTRAL: [
            "I'm happy to help you with {issue}. Let me provide you with a clear solution...",
            "Thanks for reaching out about {topic}. Here's how we can address this...",
            "I'll help you resolve {issue} efficiently. Here's what we need to do..."
        ]
    }
    
    # Response strategy adjustments by emotion
    RESPONSE_STRATEGIES = {
        EmotionalState.FRUSTRATED: {
            "tone": "calming and reassuring",
            "pace": "immediate action focus",
            "structure": "apology → quick fix → detailed solution → prevention",
            "language": "empathetic, non-technical unless necessary",
            "extras": ["offer escalation", "provide timeline"]
        },
        
        EmotionalState.CONFUSED: {
            "tone": "patient and educational", 
            "pace": "step-by-step guidance",
            "structure": "reassurance → simple explanation → guided steps → verification",
            "language": "simple, jargon-free, visual cues",
            "extras": ["offer to walk through together", "provide screenshots if relevant"]
        },
        
        EmotionalState.ANXIOUS: {
            "tone": "immediately reassuring",
            "pace": "address concerns first, then solution",
            "structure": "immediate reassurance → safety explanation → quick resolution → backup plan",
            "language": "confident, specific timelines",
            "extras": ["explain data safety", "provide backup options"]
        },
        
        EmotionalState.PROFESSIONAL: {
            "tone": "matching professionalism",
            "pace": "comprehensive and thorough", 
            "structure": "acknowledgment → detailed analysis → complete solution → optimization tips",
            "language": "technical depth appropriate, business context",
            "extras": ["advanced features", "efficiency improvements"]
        },
        
        EmotionalState.EXCITED: {
            "tone": "enthusiastic and encouraging",
            "pace": "build on excitement",
            "structure": "enthusiasm match → feature education → advanced tips → exploration encouragement",
            "language": "positive, feature-rich",
            "extras": ["advanced features", "pro tips", "hidden gems"]
        }
    }
    
    @classmethod
    def detect_emotion(cls, message: str) -> EmotionDetectionResult:
        """
        Detect customer emotional state from message content
        
        Args:
            message: Customer message text
            
        Returns:
            EmotionDetectionResult with detected emotion and confidence
        """
        scores = {}
        detected_indicators = []
        
        message_lower = message.lower()
        # Pre-compute CAPS detection once before the loop
        has_caps = any(word.isupper() and len(word) > 3 for word in message.split())
        
        for emotion, patterns in cls.EMOTION_PATTERNS.items():
            score = 0.0
            emotion_indicators = []
            
            # Check keywords
            for keyword in patterns["keywords"]:
                if keyword in message_lower:
                    score += 1.0
                    emotion_indicators.append(f"keyword: {keyword}")
            
            # Check regex patterns
            for pattern in patterns.get("patterns", []):
                matches = re.findall(pattern, message)
                if matches:
                    score += 2.0  # Patterns are stronger indicators
                    emotion_indicators.append(f"pattern: {pattern}")
            
            # Apply intensity multipliers
            multipliers = patterns.get("intensity_multipliers", {})
            for trigger, multiplier in multipliers.items():
                if trigger == "!!!" and "!!!" in message:
                    score *= multiplier
                elif trigger == "!!" and "!!" in message:
                    score *= multiplier
                elif trigger == "CAPS" and has_caps:
                    score *= multiplier
            
            if score > 0:
                scores[emotion] = score
                detected_indicators.extend(emotion_indicators)
        
        if not scores:
            return EmotionDetectionResult(
                primary_emotion=EmotionalState.NEUTRAL,
                confidence_score=0.5,
                detected_indicators=[],
                secondary_emotions=[]
            )
        
        # Sort by score and get primary emotion
        sorted_emotions = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary_emotion, primary_score = sorted_emotions[0]
        
        # Calculate confidence (normalize score)
        max_possible_score = 10.0  # Reasonable maximum
        confidence = min(primary_score / max_possible_score, 1.0)
        
        # Get secondary emotions (those with significant scores)
        secondary_emotions = [
            emotion for emotion, score in sorted_emotions[1:]
            if score >= primary_score * 0.3  # At least 30% of primary score
        ]
        
        return EmotionDetectionResult(
            primary_emotion=primary_emotion,
            confidence_score=confidence,
            detected_indicators=detected_indicators,
            secondary_emotions=secondary_emotions
        )
    
    @classmethod
    def get_empathy_template(cls, emotion: EmotionalState, issue: str = "") -> str:
        """
        Get appropriate empathy template for detected emotion
        
        Args:
            emotion: Detected emotional state
            issue: Specific issue to mention in template
            
        Returns:
            Formatted empathy template string
        """
        templates = cls.EMPATHY_TEMPLATES.get(emotion, cls.EMPATHY_TEMPLATES[EmotionalState.NEUTRAL])
        
        # Select first template (could be randomized or contextual in future)
        template = templates[0]
        
        # Replace placeholders
        if "{issue}" in template and issue:
            template = template.replace("{issue}", issue)
        elif "{topic}" in template and issue:
            template = template.replace("{topic}", issue)
        elif "{concern}" in template and issue:
            template = template.replace("{concern}", issue)
        elif "{feature}" in template and issue:
            template = template.replace("{feature}", issue)
        
        return template
    
    @classmethod
    def get_response_strategy(cls, emotion: EmotionalState) -> Dict[str, Any]:
        """Get response strategy guidelines for detected emotion"""
        return cls.RESPONSE_STRATEGIES.get(emotion, cls.RESPONSE_STRATEGIES[EmotionalState.NEUTRAL])
    
    @classmethod
    def format_emotion_aware_opening(cls, emotion_result: EmotionDetectionResult, issue: str = "") -> str:
        """
        Generate emotion-aware opening for response
        
        Args:
            emotion_result: Result from emotion detection
            issue: Specific issue to address
            
        Returns:
            Formatted empathetic opening
        """
        if emotion_result.confidence_score < 0.3:
            # Low confidence, use neutral opening
            emotion = EmotionalState.NEUTRAL
        else:
            emotion = emotion_result.primary_emotion
            
        return cls.get_empathy_template(emotion, issue)