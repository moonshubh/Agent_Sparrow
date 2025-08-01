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
                "worst", "hate", "frustrated", "annoying", "ridiculous", "pathetic",
                "fed up", "sick of", "tired of", "angry", "pissed", "mad",
                "garbage", "trash", "crap", "sucks", "fail", "failing",
                "never works", "always breaks", "constantly", "keeps happening"
            ],
            "patterns": [
                r"(?i)this is (so |really )?(stupid|ridiculous|broken)",
                r"(?i)(completely|totally|absolutely) (broken|useless)",
                r"(?i)doesn't work( at all)?",
                r"(?i)waste of (time|money)",
                r"(?i)nothing works",
                r"(?i)why (doesn't|won't) (this|it)",
                r"(?i)(sick|tired) of (this|dealing with)",
                r"(?i)every (damn |single )?time",
                r"!!{2,}",  # Multiple exclamation marks
                r"[A-Z]{10,}",  # Long caps sequences
                r"\?{3,}",  # Multiple question marks (frustration)
            ],
            "intensity_multipliers": {
                "!!": 1.2,
                "!!!": 1.5,
                "!!!!+": 2.0, 
                "CAPS": 1.3,
                "profanity": 1.8,
                "multiple_issues": 1.4  # "nothing works AND this is broken AND..."
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
                "emergency", "critical", "losing", "lost", "missing", "scared",
                "panicking", "freaking out", "help", "desperate", "immediately",
                "right now", "can't lose", "backup", "recover", "afraid"
            ],
            "patterns": [
                r"(?i)(urgent|emergency|critical|important)",
                r"(?i)need (this|it) (today|now|asap|immediately)",
                r"(?i)(worried|concerned|scared|afraid) (about|that)",
                r"(?i)(losing|lost|missing) (emails|data|messages|files)",
                r"(?i)deadline",
                r"(?i)can't afford to",
                r"(?i)please help",
                r"(?i)(freaking|stressing) out",
                r"(?i)what if (I|i've) lost",
                r"(?i)need (to|this) work(ing)? (now|today)"
            ],
            "intensity_multipliers": {
                "all_caps_help": 1.5,  # "HELP" or "URGENT"
                "multiple_urgent": 1.3,  # Multiple urgency indicators
                "time_pressure": 1.4  # "in 5 minutes", "by noon", etc.
            }
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
    
    # Empathy response templates by emotion - Hemingway clarity + Oprah warmth
    EMPATHY_TEMPLATES = {
        EmotionalState.FRUSTRATED: [
            "Oh, {issue} is maddening! I get it. Let's fix this right now.",
            "That's infuriating when {issue} happens. You shouldn't have to deal with this. Here's the fix.",
            "I hear you - {issue} is the worst. Let me make this right, fast."
        ],
        
        EmotionalState.CONFUSED: [
            "Hey, {topic} trips everyone up! Let me break it down super simply.",
            "{topic} is confusing - you're not alone! Here's the easy way.",
            "No worries - {topic} makes zero sense until someone explains it properly. That's what I'm here for!"
        ],
        
        EmotionalState.ANXIOUS: [
            "First, breathe - your emails are safe. {concern} is fixable. Here's how.",
            "I know {issue} feels scary. Your data is secure. Let's solve this together.",
            "Don't panic about {concern}. Everything's backed up. Here's what we'll do."
        ],
        
        EmotionalState.PROFESSIONAL: [
            "Thanks for reaching out about {issue}. Here's your solution.",
            "I'll handle {topic} efficiently for you. Let's dive in.",
            "Regarding {issue} - here's exactly what you need."
        ],
        
        EmotionalState.EXCITED: [
            "Your enthusiasm about {topic} is awesome! Wait till you see this...",
            "Love the energy! {feature} gets even better. Check this out.",
            "You're excited about {topic}? Oh, you're going to LOVE what's next!"
        ],
        
        EmotionalState.URGENT: [
            "Time's critical. Here's the fastest fix for {issue}.",
            "I see the urgency. Quick solution for {issue} coming up.",
            "No time to waste. {issue} fixed in 3 steps. Go!"
        ],
        
        EmotionalState.DISAPPOINTED: [
            "I'm sorry {issue} let you down. That's on us. Let me fix it.",
            "{issue} should work better. You're right. Here's how we'll make it right.",
            "You expected better from {issue}, and you should have gotten it. Let's turn this around."
        ],
        
        EmotionalState.NEUTRAL: [
            "Happy to help with {issue}. Here's what you need.",
            "{topic}? I've got you covered.",
            "Let's solve {issue} quickly and easily."
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
        },
        
        EmotionalState.URGENT: {
            "tone": "immediate and action-focused",
            "pace": "fast and direct",
            "structure": "immediate action → quick solution → verification → follow-up",
            "language": "concise, time-conscious",
            "extras": ["priority handling", "escalation options"]
        },
        
        EmotionalState.DISAPPOINTED: {
            "tone": "understanding and recovery-focused",
            "pace": "acknowledge disappointment then rebuild confidence",
            "structure": "acknowledgment → apology → enhanced solution → relationship repair",
            "language": "empathetic, solution-oriented",
            "extras": ["exceed expectations", "prevent recurrence"]
        },
        
        EmotionalState.NEUTRAL: {
            "tone": "professional and helpful",
            "pace": "steady and thorough",
            "structure": "greeting → clear solution → verification → assistance offer",
            "language": "clear, professional, informative",
            "extras": ["efficiency tips", "additional resources"]
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
            
            # Apply intensity multipliers with capping to prevent excessive inflation
            multipliers = patterns.get("intensity_multipliers", {})
            total_multiplier = 1.0
            exclamation_applied = False
            
            for trigger, multiplier in multipliers.items():
                # Handle exclamation marks with priority (only apply one)
                if trigger == "!!!!+" and "!!!!" in message and not exclamation_applied:
                    total_multiplier *= multiplier
                    exclamation_applied = True
                elif trigger == "!!!" and "!!!" in message and not exclamation_applied:
                    total_multiplier *= multiplier
                    exclamation_applied = True
                elif trigger == "!!" and "!!" in message and not exclamation_applied:
                    total_multiplier *= multiplier
                    exclamation_applied = True
                
                # Handle other multipliers independently
                elif trigger == "CAPS" and has_caps:
                    total_multiplier *= min(multiplier, 1.5)  # Cap CAPS multiplier
                elif trigger == "all_caps_help" and any(word in message for word in ["HELP", "URGENT", "ASAP"]):
                    total_multiplier *= min(multiplier, 1.4)  # Cap help multiplier
                elif trigger == "multiple_urgent" and sum(1 for word in ["urgent", "asap", "now", "immediately"] if word in message_lower) >= 2:
                    total_multiplier *= min(multiplier, 1.3)  # Cap urgent multiplier
                elif trigger == "time_pressure" and re.search(r"(?i)(in \d+ (minutes?|hours?)|by \d+|before \d+)", message):
                    total_multiplier *= min(multiplier, 1.4)  # Cap time pressure multiplier
                elif trigger == "multiple_issues" and cls._detect_multiple_issues(message_lower):
                    total_multiplier *= min(multiplier, 1.4)  # Cap multiple issues multiplier
            
            # Cap the total multiplier to prevent score inflation
            total_multiplier = min(total_multiplier, 3.0)
            score *= total_multiplier
            
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
    def _detect_multiple_issues(cls, message_lower: str) -> bool:
        """
        Improved detection for multiple issues to reduce false positives.
        
        Args:
            message_lower: Lowercase message content
            
        Returns:
            True if multiple distinct issues are detected
        """
        # Look for issue patterns rather than just counting "and"
        issue_indicators = [
            "can't", "cannot", "doesn't", "won't", "not working", "broken",
            "error", "problem", "issue", "trouble", "fail", "crash",
            "stuck", "help", "missing", "lost", "slow", "freeze",
            # Expanded issue indicators
            "stopped working", "not responding", "won't load", "keeps crashing",
            "timeout", "connection failed", "sync error", "login failed",
            "can't connect", "authentication", "blocked", "denied",
            "corrupted", "damaged", "invalid", "expired", "outdated"
        ]
        
        # Count distinct issue indicators
        issue_count = sum(1 for indicator in issue_indicators if indicator in message_lower)
        
        # Multiple issues if we have 2+ issue indicators AND connector words
        connectors = ["and", "also", "plus", "additionally", "furthermore", "moreover"]
        has_connectors = any(connector in message_lower for connector in connectors)
        
        return issue_count >= 2 and has_connectors
    
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