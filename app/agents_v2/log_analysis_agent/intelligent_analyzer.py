"""
Intelligent Log Analysis Engine powered by Gemini 2.5 Pro
Leverages advanced AI reasoning for comprehensive log analysis and solution generation.
"""

import os
import json
import time
from typing import Dict, Any, List
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.settings import settings
from app.core.logging_config import get_logger

class IntelligentLogAnalyzer:
    """
    Advanced log analyzer that leverages Gemini 2.5 Pro's reasoning capabilities
    for intelligent pattern detection, root cause analysis, and solution generation.
    """
    
    def __init__(self):
        self.reasoning_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            temperature=0.1,  # Low temperature for consistent analysis
            google_api_key=settings.gemini_api_key,
        )
        
        # System instructions for the AI analyst
        self.system_instructions = """
You are a SENIOR MAILBIRD TECHNICAL SPECIALIST with 10+ years of experience in enterprise email systems. You have expertise in:

**TECHNICAL DOMAINS:**
- Email protocols: IMAP, SMTP, POP3, Exchange ActiveSync, OAuth2 authentication flows
- Network diagnostics: DNS resolution, firewall configurations, power management
- Account-specific troubleshooting: Provider settings, authentication methods, connection patterns
- System integration: Windows power states, registry settings, service dependencies
- Performance optimization: Connection pooling, timeout configurations, retry logic

**ANALYSIS METHODOLOGY:**
1. **TIMELINE ANALYSIS**: Track issues chronologically to identify patterns and triggers
2. **ACCOUNT-SPECIFIC DIAGNOSIS**: Analyze each email account individually with provider-specific knowledge
3. **ROOT CAUSE IDENTIFICATION**: Go beyond symptoms to identify underlying technical causes
4. **CONTEXTUAL SOLUTION DESIGN**: Provide specific technical implementations with exact settings
5. **PROFESSIONAL DOCUMENTATION**: Create enterprise-grade reports suitable for IT managers

**OUTPUT REQUIREMENTS:**
- Extract SPECIFIC EMAIL ADDRESSES and analyze each account's unique issues
- Identify EXACT ERROR PATTERNS with technical context
- Provide SPECIFIC TECHNICAL SOLUTIONS with server settings, ports, and configuration steps
- Include QUANTIFIED OUTCOMES and implementation timelines
- Use PROFESSIONAL TECHNICAL LANGUAGE appropriate for IT staff

**QUALITY STANDARDS:**
- Every solution must include specific technical details (server names, ports, settings)
- Account analysis must be individualized with email addresses
- Timeline must be specific (dates, times, event sequences)
- Implementation steps must be actionable with exact commands/settings
"""

    async def perform_intelligent_analysis(self, raw_log_content: str, basic_parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform comprehensive intelligent analysis using Gemini 2.5 Pro's reasoning capabilities.
        """
        logger = get_logger("intelligent_analyzer")
        
        # Phase 1: Pattern Recognition and Issue Identification
        logger.info("Starting intelligent pattern analysis...")
        issues_analysis = await self._analyze_patterns_and_issues(raw_log_content, basic_parsed_data)
        
        # Phase 2: Root Cause Analysis
        logger.info("Performing root cause analysis...")
        root_cause_analysis = await self._perform_root_cause_analysis(raw_log_content, issues_analysis)
        
        # Phase 3: Solution Generation
        logger.info("Generating intelligent solutions...")
        intelligent_solutions = await self._generate_intelligent_solutions(issues_analysis, root_cause_analysis)
        
        # Phase 4: Executive Summary
        logger.info("Creating executive summary...")
        executive_summary = await self._create_executive_summary(
            raw_log_content, issues_analysis, root_cause_analysis, intelligent_solutions
        )
        
        return {
            'issues_analysis': issues_analysis,
            'root_cause_analysis': root_cause_analysis,
            'intelligent_solutions': intelligent_solutions,
            'executive_summary': executive_summary,
            'analysis_metadata': {
                'analyzer_version': '2.0-intelligent',
                'ai_model': 'gemini-2.5-pro',
                'analysis_timestamp': datetime.utcnow().isoformat(),
                'reasoning_approach': 'step-by-step-thinking'
            }
        }

    async def _analyze_patterns_and_issues(self, raw_log_content: str, basic_parsed_data: Dict) -> Dict[str, Any]:
        """Use Gemini 2.5 Pro to identify complex patterns and issues."""
        
        prompt = f"""
{self.system_instructions}

## TASK: COMPREHENSIVE PATTERN ANALYSIS

Analyze the following Mailbird log data for patterns, issues, and anomalies.

### BASIC PARSED DATA:
```json
{json.dumps(basic_parsed_data, indent=2)}
```

### FULL LOG CONTENT:
```
{raw_log_content[:50000]}  # Limit to fit context window efficiently
```

## COMPREHENSIVE ANALYSIS REQUIREMENTS:

**MANDATORY ACCOUNT EXTRACTION:**
- Extract ALL email addresses from logs (format: name@domain.com)
- Analyze EACH account individually with provider-specific knowledge
- Track connection patterns, authentication methods, and provider settings per account

**TECHNICAL PATTERN RECOGNITION:**
- IMAP/SMTP server connection patterns and failures
- OAuth2 authentication flows and token refresh issues
- Power management correlation with connection drops
- DNS resolution problems and network instability
- Provider-specific issues (Gmail, Outlook, Shaw, Yahoo, etc.)

**DETAILED TECHNICAL ANALYSIS:**
- Exact error messages with technical context
- Server names, ports, and connection protocols
- Authentication methods and credential validation
- Network adapter and power management correlation
- Timeline analysis with specific timestamps

## OUTPUT FORMAT:
Provide detailed JSON analysis with this enhanced structure:

```json
{{
  "account_analysis": [
    {{
      "email_address": "aeyates@shaw.ca",
      "provider": "Shaw Communications",
      "primary_issues": ["IMAP authentication failures", "connection drops"],
      "server_details": {{
        "imap_server": "imap.shaw.ca",
        "smtp_server": "smtp.shaw.ca",
        "detected_ports": ["993", "587"],
        "authentication_method": "basic|oauth2|app_password"
      }},
      "error_patterns": [
        {{
          "error_type": "IMAP server terminating connection",
          "frequency": 15,
          "first_occurrence": "2025-05-25 09:15:32",
          "last_occurrence": "2025-05-29 16:42:18"
        }}
      ],
      "issue_severity": "critical|high|medium|low",
      "recommended_action": "Specific technical recommendation"
    }}
  ],
  "technical_patterns": [
    {{
      "pattern_name": "Power Management Connection Drops",
      "technical_signature": "SystemEvents.PowerModeChanged: Resume followed by connection failures",
      "affected_accounts": ["all accounts"],
      "frequency_analysis": "Every system resume event",
      "root_cause": "Network adapter power saving mode",
      "impact_assessment": "90% of connection drops occur within 30 seconds of system resume"
    }}
  ],
  "critical_findings": [
    {{
      "finding": "Shaw IMAP Server Authentication Failures",
      "technical_details": "IMAP server terminating connection errors specific to @shaw.ca accounts",
      "affected_accounts": ["aeyates@shaw.ca", "pyates@shaw.ca"],
      "evidence": ["specific log entries demonstrating the pattern"],
      "business_impact": "Complete email disruption for Shaw accounts"
    }}
  ],
  "system_timeline": {{
    "analysis_period": "2025-05-25 to 2025-05-29",
    "major_events": [
      {{
        "timestamp": "2025-05-28 14:30:00",
        "event": "pyates@shaw.ca account removed and re-added",
        "impact": "Temporary resolution of authentication issues"
      }}
    ],
    "peak_issue_periods": ["09:00-10:00 daily", "after system resume events"]
  }}
}}
```

THINK STEP BY STEP and provide comprehensive analysis.
"""
        
        try:
            response = await self.reasoning_llm.ainvoke(prompt)
            # Extract JSON from response
            response_text = response.content
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                json_content = response_text[json_start:json_end].strip()
            else:
                json_content = response_text
            
            return json.loads(json_content)
        except Exception as e:
            return {
                "error": f"Pattern analysis failed: {str(e)}",
                "identified_patterns": [],
                "issue_categories": {},
                "system_health_score": {"overall_score": 0, "stability_rating": "unknown"},
                "temporal_insights": {}
            }

    async def _perform_root_cause_analysis(self, raw_log_content: str, issues_analysis: Dict) -> Dict[str, Any]:
        """Perform deep root cause analysis using AI reasoning."""
        
        prompt = f"""
{self.system_instructions}

## TASK: ROOT CAUSE ANALYSIS

Based on the identified patterns and issues, perform deep root cause analysis.

### IDENTIFIED ISSUES:
```json
{json.dumps(issues_analysis, indent=2)}
```

### LOG SAMPLE FOR CONTEXT:
```
{raw_log_content[:30000]}
```

## ANALYSIS REQUIREMENTS:

1. **Technical Root Causes**: Identify underlying technical causes, not just symptoms
2. **System Interactions**: How different components interact and fail
3. **Configuration Issues**: Identify potential misconfigurations
4. **Environmental Factors**: Network, system resources, external dependencies
5. **Progressive Issues**: How small issues can cascade into larger problems

## OUTPUT FORMAT:
```json
{{
  "primary_root_causes": [
    {{
      "issue_id": "oauth2_refresh_failure",
      "root_cause": "DNS resolution failure preventing OAuth2 token refresh",
      "technical_explanation": "Detailed technical explanation of the underlying cause",
      "evidence_from_logs": ["specific log entries that support this conclusion"],
      "system_components_involved": ["DNS resolver", "OAuth2 client", "Network stack"],
      "configuration_factors": ["Network adapter power management", "DNS cache settings"],
      "likelihood_score": 0.95
    }}
  ],
  "contributing_factors": [
    {{
      "factor": "Power management settings",
      "impact_level": "high|medium|low",
      "description": "How this factor contributes to the issues"
    }}
  ],
  "cascading_effects": [
    {{
      "trigger": "Network adapter power-down",
      "cascade": ["Connection lost", "Authentication failure", "Sync interruption"],
      "mitigation_points": ["Where in the cascade intervention is possible"]
    }}
  ]
}}
```

THINK THROUGH THE TECHNICAL DETAILS and provide expert-level root cause analysis.
"""
        
        try:
            response = await self.reasoning_llm.ainvoke(prompt)
            response_text = response.content
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                json_content = response_text[json_start:json_end].strip()
            else:
                json_content = response_text
            
            return json.loads(json_content)
        except Exception as e:
            return {
                "error": f"Root cause analysis failed: {str(e)}",
                "primary_root_causes": [],
                "contributing_factors": [],
                "cascading_effects": []
            }

    async def _generate_intelligent_solutions(self, issues_analysis: Dict, root_cause_analysis: Dict) -> List[Dict[str, Any]]:
        """Generate intelligent, contextual solutions using AI reasoning."""
        
        prompt = f"""
{self.system_instructions}

## TASK: INTELLIGENT SOLUTION GENERATION

Generate comprehensive, actionable solutions based on the analysis.

### ISSUES ANALYSIS:
```json
{json.dumps(issues_analysis, indent=2)}
```

### ROOT CAUSE ANALYSIS:
```json
{json.dumps(root_cause_analysis, indent=2)}
```

## ENTERPRISE-GRADE SOLUTION REQUIREMENTS:

**ACCOUNT-SPECIFIC SOLUTIONS:**
- Provide solutions tailored to specific email providers (Gmail, Outlook, Shaw, Yahoo)
- Include exact server settings: server names, ports, encryption methods
- Specify authentication methods and credential requirements
- Address provider-specific known issues and configurations

**TECHNICAL IMPLEMENTATION DETAILS:**
- Exact commands, registry entries, and configuration file paths
- Specific Windows settings and Device Manager configurations
- Network adapter settings and power management options
- DNS configuration and firewall rule specifications

**PROFESSIONAL DOCUMENTATION:**
- Implementation timeline with priority levels (Critical, High, Medium)
- Quantified success metrics with measurable outcomes
- Risk assessment with probability ratings and mitigation strategies
- Follow-up monitoring procedures and validation steps

## OUTPUT FORMAT:
```json
[
  {{
    "solution_id": "shaw_imap_authentication_fix",
    "title": "Resolve Shaw IMAP Server Authentication Failures",
    "priority": "Critical",
    "affected_accounts": ["aeyates@shaw.ca", "pyates@shaw.ca"],
    "target_root_causes": ["shaw_imap_termination", "authentication_timeout"],
    "estimated_resolution_time": "15-30 minutes",
    "success_probability": "High",
    "expected_outcome": "90% reduction in Shaw IMAP authentication failures",
    "implementation_steps": [
      {{
        "step_number": 1,
        "action": "Verify Shaw IMAP server settings",
        "details": {{
          "server": "imap.shaw.ca",
          "port": "993",
          "encryption": "SSL/TLS",
          "authentication_method": "Normal password"
        }},
        "command": "Check Account Settings > Advanced > Incoming Mail (IMAP) Settings",
        "expected_outcome": "Confirms correct server configuration",
        "verification": "Test connection using 'Test Account Settings'",
        "estimated_time": "5 minutes"
      }},
      {{
        "step_number": 2,
        "action": "Configure app-specific password for Shaw accounts",
        "details": {{
          "login_url": "https://my.shaw.ca",
          "navigation": "My Account > Security > App Passwords",
          "password_type": "Email application password"
        }},
        "command": "Generate new app-specific password",
        "expected_outcome": "Eliminates authentication timeouts",
        "verification": "Successful IMAP connection without termination",
        "estimated_time": "10 minutes"
      }}
    ],
    "prerequisites": ["Shaw account access", "Administrator privileges on Windows"],
    "technical_specifications": {{
      "imap_server": "imap.shaw.ca",
      "imap_port": 993,
      "smtp_server": "smtp.shaw.ca", 
      "smtp_port": 587,
      "encryption": "TLS/SSL",
      "authentication": "App-specific password recommended"
    }},
    "risks": [
      {{
        "risk": "Temporary email disruption during reconfiguration",
        "probability": "Low",
        "mitigation": "Perform during low-usage hours",
        "duration": "5-10 minutes maximum"
      }}
    ],
    "success_metrics": [
      "Zero 'IMAP server terminating connection' errors for Shaw accounts",
      "Successful authentication for 100% of connection attempts",
      "Stable email synchronization for 24+ hours post-implementation"
    ],
    "alternative_approaches": [
      "Remove and re-add Shaw accounts with fresh authentication",
      "Configure Shaw accounts using POP3 instead of IMAP",
      "Contact Shaw technical support for server status verification"
    ],
    "follow_up_actions": [
      "Monitor Shaw account connections for 48 hours",
      "Document app-specific passwords in secure password manager",
      "Schedule monthly password rotation reminder"
    ],
    "quantified_impact": "Eliminates 100% of Shaw-specific authentication failures affecting 2 accounts",
    "technical_notes": "Shaw Communications requires app-specific passwords for IMAP access due to enhanced security measures. Standard passwords may cause intermittent authentication failures."
  }}
]
```

GENERATE PRACTICAL, EXPERT-LEVEL SOLUTIONS that address the identified root causes.
"""
        
        try:
            response = await self.reasoning_llm.ainvoke(prompt)
            response_text = response.content
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                json_content = response_text[json_start:json_end].strip()
            else:
                json_content = response_text
            
            return json.loads(json_content)
        except Exception as e:
            return [{
                "solution_id": "error_fallback",
                "title": "Contact Technical Support",
                "priority": "High",
                "error": f"Solution generation failed: {str(e)}",
                "implementation_steps": [
                    {
                        "step_number": 1,
                        "action": "Contact Mailbird technical support with log file",
                        "expected_outcome": "Professional analysis and resolution"
                    }
                ]
            }]

    async def _create_executive_summary(self, raw_log_content: str, issues_analysis: Dict, 
                                       root_cause_analysis: Dict, solutions: List[Dict]) -> str:
        """Create a comprehensive executive summary in markdown format."""
        
        # Count log entries separately to avoid f-string backslash issue
        log_entry_count = len(raw_log_content.split('\n'))
        analysis_timestamp = datetime.utcnow().isoformat()
        
        prompt = f"""
{self.system_instructions}

## TASK: EXECUTIVE SUMMARY CREATION

Create a comprehensive executive summary in professional markdown format.

### ANALYSIS DATA:
- Issues Analysis: {json.dumps(issues_analysis, indent=2)[:5000]}
- Root Cause Analysis: {json.dumps(root_cause_analysis, indent=2)[:5000]}
- Solutions: {json.dumps(solutions, indent=2)[:5000]}

### LOG METADATA:
- Log entries analyzed: {log_entry_count}
- Analysis timestamp: {analysis_timestamp}

## EXECUTIVE SUMMARY REQUIREMENTS:

Create a comprehensive executive summary following this EXACT professional structure:

**REQUIRED SECTIONS:**

1. **## Executive Summary** 
   - 2-3 sentence overview mentioning specific timeframe and affected accounts
   - Highlight primary problems (authentication failures, connection drops, etc.)
   - State impact level and affected account count

2. **## Key Issues Identified**
   - **### 1. [Issue Name] (Critical/High/Medium)**
   - **Pattern**: Specific technical pattern description
   - **Affected Accounts**: List exact email addresses
   - **Frequency**: Quantified occurrence data
   - **Impact**: Business impact description

3. **## Account-Specific Issues**
   - Create markdown table with columns: Account | Primary Issues | Status
   - Include all discovered email addresses with individual analysis

4. **## Recommended Solutions**
   - **### Immediate Actions (Critical)**
   - **### Short-term Solutions (High Priority)** 
   - **### Long-term Solutions (Medium Priority)**
   - Each solution with specific technical steps and server settings

5. **## Expected Outcomes**
   - Quantified improvements (e.g., "90% reduction in connection drops")
   - Specific resolution targets for each issue type

6. **## Priority Implementation Order**
   - Day 1, Day 2, Week 1, Week 2 timeline
   - Specific actions with priority levels

## PROFESSIONAL FORMATTING STANDARDS:
- Use specific email addresses, server names, and technical details
- Include exact timeframes and quantified metrics
- Provide actionable technical instructions
- Format as professional IT documentation suitable for management review

GENERATE A COMPREHENSIVE, PROFESSIONAL EXECUTIVE SUMMARY.
"""
        
        try:
            response = await self.reasoning_llm.ainvoke(prompt)
            return response.content
        except Exception as e:
            return f"""# Executive Summary - Log Analysis Report

## ⚠️ Analysis Error

An error occurred while generating the executive summary: {str(e)}

Please contact technical support for manual analysis.

### Immediate Actions Required:
1. Save the original log file
2. Contact Mailbird technical support
3. Provide error details for troubleshooting

---
*Generated by Intelligent Log Analyzer v2.0*
"""

# Main entry point
async def perform_intelligent_log_analysis(raw_log_content: str, basic_parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point for intelligent log analysis using Gemini 2.5 Pro reasoning.
    """
    analyzer = IntelligentLogAnalyzer()
    return await analyzer.perform_intelligent_analysis(raw_log_content, basic_parsed_data)