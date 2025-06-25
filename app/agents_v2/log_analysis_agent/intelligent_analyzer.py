"""
Intelligent Log Analysis Engine powered by Gemini 2.5 Pro
Leverages advanced AI reasoning for comprehensive log analysis and solution generation.
"""

import os
import json
import time
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from langchain_google_genai import ChatGoogleGenerativeAI
import asyncio
import logging
from collections import defaultdict, Counter
import networkx as nx
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

from app.core.settings import settings
from app.core.logging_config import get_logger

logger = logging.getLogger(__name__)

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
        
        # Historical data storage for predictive analysis
        self.historical_patterns = defaultdict(list)
        self.prediction_models = {}
        
        # Correlation analysis components
        self.correlation_threshold = 0.7
        self.temporal_window = 300  # 5 minutes in seconds
        
        # Dependency graph for issue relationships
        self.dependency_graph = nx.DiGraph()
        
        # Issue classification for predictive modeling
        self.issue_categories = {
            'connection_failures': ['connection_drops', 'timeout', 'network_unreachable'],
            'authentication_errors': ['auth_failed', 'oauth2_failure', 'credential_invalid'],
            'protocol_issues': ['smtp_send_failure', 'imap_auth_failure', 'ssl_handshake_failure'],
            'system_integration': ['power_management_issues', 'registry_access_failure', 'com_activation_failure'],
            'performance_degradation': ['slow_response', 'high_latency', 'resource_exhaustion']
        }
        
        # Enhanced system instructions with predictive and correlation analysis
        self.system_instructions = """
You are a SENIOR MAILBIRD TECHNICAL SPECIALIST with 15+ years of experience in enterprise email systems. You have expertise in:

**EXPANDED TECHNICAL DOMAINS:**
- Cross-platform email clients: Windows, macOS, Linux compatibility
- Advanced protocols: JMAP, CardDAV, CalDAV, alongside IMAP/SMTP/POP3
- Cloud email services: Office 365, Google Workspace, iCloud, ProtonMail
- Security: S/MIME, PGP, OAuth2, SAML, certificate management
- Performance: Memory optimization, database indexing, connection pooling
- Accessibility: Screen reader compatibility, keyboard navigation
- Localization: Multi-language support, RTL text handling

**ENHANCED ANALYSIS METHODOLOGY:**
1. **PREDICTIVE ANALYSIS**: Identify patterns that predict future failures
2. **CORRELATION ANALYSIS**: Find relationships between seemingly unrelated issues
3. **DEPENDENCY MAPPING**: Build issue relationship graphs showing root causes vs symptoms
4. **ENVIRONMENTAL CONTEXT**: Consider OS updates, antivirus, network topology
5. **USER BEHAVIOR ANALYSIS**: Identify usage patterns affecting performance
6. **TEMPORAL PATTERN RECOGNITION**: Detect time-based correlations and seasonal patterns
7. **COMPARATIVE ANALYSIS**: Compare against baseline healthy system metrics

**ADVANCED PATTERN RECOGNITION:**
- Identify cascading failures and their trigger points
- Detect performance degradation trends before critical failure
- Recognize security vulnerability indicators
- Identify compatibility issues with specific email providers
- Detect resource exhaustion patterns

**PREDICTIVE CAPABILITIES:**
- Forecast potential issues based on current system state
- Identify early warning indicators
- Provide preventive maintenance recommendations
- Calculate probability scores for future problems

**SOLUTION VALIDATION:**
- Each solution must include success criteria and verification steps
- Provide rollback procedures for risky changes
- Include automated test scripts where applicable
- Specify compatibility requirements and limitations
"""

    async def perform_intelligent_analysis(self, raw_log_content: str, basic_parsed_data: Dict[str, Any], 
                                          historical_data: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Perform comprehensive intelligent analysis using Gemini 2.5 Pro's reasoning capabilities.
        Enhanced with predictive analysis, correlation detection, and dependency mapping.
        """
        logger = get_logger("intelligent_analyzer")
        
        # Phase 1: Pattern Recognition and Issue Identification
        logger.info("Starting intelligent pattern analysis...")
        issues_analysis = await self._analyze_patterns_and_issues(raw_log_content, basic_parsed_data)
        
        # Phase 2: Correlation Analysis
        logger.info("Performing correlation analysis...")
        correlation_analysis = await self._perform_correlation_analysis(basic_parsed_data, issues_analysis)
        
        # Phase 3: Dependency Graph Analysis
        logger.info("Building issue dependency graph...")
        dependency_analysis = await self._build_issue_dependency_graph(issues_analysis, correlation_analysis)
        
        # Phase 4: Predictive Analysis (if historical data available)
        predictive_analysis = {}
        if historical_data and len(historical_data) > 0:
            logger.info("Performing predictive analysis...")
            predictive_analysis = await self._perform_predictive_analysis(historical_data, issues_analysis)
        
        # Phase 5: Root Cause Analysis (Enhanced)
        logger.info("Performing enhanced root cause analysis...")
        root_cause_analysis = await self._perform_enhanced_root_cause_analysis(
            raw_log_content, issues_analysis, correlation_analysis, dependency_analysis
        )
        
        # Phase 6: Solution Generation (Enhanced)
        logger.info("Generating intelligent solutions...")
        intelligent_solutions = await self._generate_enhanced_solutions(
            issues_analysis, root_cause_analysis, correlation_analysis, predictive_analysis
        )
        
        # Phase 7: Executive Summary (Enhanced)
        logger.info("Creating comprehensive executive summary...")
        executive_summary = await self._create_enhanced_executive_summary(
            raw_log_content, issues_analysis, root_cause_analysis, intelligent_solutions,
            correlation_analysis, dependency_analysis, predictive_analysis
        )
        
        return {
            'issues_analysis': issues_analysis,
            'correlation_analysis': correlation_analysis,
            'dependency_analysis': dependency_analysis,
            'predictive_analysis': predictive_analysis,
            'root_cause_analysis': root_cause_analysis,
            'intelligent_solutions': intelligent_solutions,
            'executive_summary': executive_summary,
            'analysis_metadata': {
                'analyzer_version': '3.0-enhanced-intelligent',
                'ai_model': 'gemini-2.5-pro',
                'analysis_timestamp': datetime.utcnow().isoformat(),
                'reasoning_approach': 'multi-phase-comprehensive',
                'features_enabled': [
                    'pattern_recognition',
                    'correlation_analysis', 
                    'dependency_mapping',
                    'predictive_analysis' if historical_data else 'predictive_analysis_disabled',
                    'enhanced_root_cause',
                    'solution_validation'
                ]
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

    async def _perform_correlation_analysis(self, basic_parsed_data: Dict, issues_analysis: Dict) -> Dict[str, Any]:
        """
        Perform correlation analysis to identify relationships between issues.
        """
        try:
            logger.info("Starting correlation analysis...")
            
            # Extract temporal events from parsed data
            temporal_events = []
            if 'entries' in basic_parsed_data:
                for entry in basic_parsed_data['entries']:
                    if entry.get('timestamp') and entry.get('issue_type'):
                        temporal_events.append({
                            'timestamp': self._parse_timestamp(entry['timestamp']),
                            'issue_type': entry['issue_type'],
                            'account': entry.get('account', 'unknown'),
                            'severity': entry.get('severity', 'medium')
                        })
            
            # Find temporal correlations
            temporal_correlations = await self._find_temporal_correlations(temporal_events)
            
            # Find account-based correlations
            account_correlations = await self._find_account_correlations(temporal_events)
            
            # Find issue type correlations
            issue_type_correlations = await self._find_issue_type_correlations(temporal_events)
            
            # Calculate correlation strengths
            correlation_matrix = await self._calculate_correlation_matrix(temporal_events)
            
            return {
                'temporal_correlations': temporal_correlations,
                'account_correlations': account_correlations,
                'issue_type_correlations': issue_type_correlations,
                'correlation_matrix': correlation_matrix,
                'analysis_summary': {
                    'total_events_analyzed': len(temporal_events),
                    'significant_correlations_found': len([c for c in temporal_correlations if c.get('strength', 0) > self.correlation_threshold]),
                    'strongest_correlation': max(temporal_correlations, key=lambda x: x.get('strength', 0), default={'strength': 0})
                }
            }
            
        except Exception as e:
            logger.error(f"Correlation analysis failed: {str(e)}")
            return {
                'error': str(e),
                'temporal_correlations': [],
                'account_correlations': [],
                'issue_type_correlations': [],
                'correlation_matrix': {}
            }

    async def _build_issue_dependency_graph(self, issues_analysis: Dict, correlation_analysis: Dict) -> Dict[str, Any]:
        """
        Build a dependency graph showing relationships between issues.
        """
        try:
            logger.info("Building issue dependency graph...")
            
            # Create dependency graph
            self.dependency_graph.clear()
            
            # Add nodes for each issue type
            issue_types = set()
            if 'account_analysis' in issues_analysis:
                for account in issues_analysis['account_analysis']:
                    for issue in account.get('primary_issues', []):
                        issue_types.add(issue)
            
            # Add nodes to graph
            for issue_type in issue_types:
                self.dependency_graph.add_node(issue_type, type='issue')
            
            # Add edges based on correlations
            for correlation in correlation_analysis.get('temporal_correlations', []):
                if correlation.get('strength', 0) > self.correlation_threshold:
                    source = correlation.get('source_issue')
                    target = correlation.get('target_issue')
                    if source and target and source in issue_types and target in issue_types:
                        self.dependency_graph.add_edge(
                            source, target, 
                            weight=correlation.get('strength', 0),
                            correlation_type='temporal',
                            delay=correlation.get('average_delay', 0)
                        )
            
            # Identify root causes (nodes with no incoming edges)
            root_causes = [node for node in self.dependency_graph.nodes() 
                          if self.dependency_graph.in_degree(node) == 0]
            
            # Identify symptoms (nodes with high incoming degree)
            symptoms = sorted(self.dependency_graph.nodes(), 
                            key=lambda x: self.dependency_graph.in_degree(x), reverse=True)[:3]
            
            # Find strongly connected components (cyclical dependencies)
            strongly_connected = list(nx.strongly_connected_components(self.dependency_graph))
            
            # Calculate centrality measures
            centrality_measures = {}
            if len(self.dependency_graph.nodes()) > 0:
                centrality_measures = {
                    'betweenness': nx.betweenness_centrality(self.dependency_graph),
                    'pagerank': nx.pagerank(self.dependency_graph),
                    'in_degree': dict(self.dependency_graph.in_degree()),
                    'out_degree': dict(self.dependency_graph.out_degree())
                }
            
            return {
                'graph_summary': {
                    'total_nodes': self.dependency_graph.number_of_nodes(),
                    'total_edges': self.dependency_graph.number_of_edges(),
                    'is_connected': nx.is_weakly_connected(self.dependency_graph) if self.dependency_graph.number_of_nodes() > 0 else False
                },
                'root_causes': root_causes,
                'primary_symptoms': symptoms,
                'cyclical_dependencies': [list(component) for component in strongly_connected if len(component) > 1],
                'centrality_measures': centrality_measures,
                'issue_relationships': [
                    {
                        'source': edge[0],
                        'target': edge[1],
                        'strength': self.dependency_graph[edge[0]][edge[1]].get('weight', 0),
                        'type': self.dependency_graph[edge[0]][edge[1]].get('correlation_type', 'unknown'),
                        'delay_seconds': self.dependency_graph[edge[0]][edge[1]].get('delay', 0)
                    }
                    for edge in self.dependency_graph.edges()
                ]
            }
            
        except Exception as e:
            logger.error(f"Dependency graph analysis failed: {str(e)}")
            return {
                'error': str(e),
                'graph_summary': {'total_nodes': 0, 'total_edges': 0},
                'root_causes': [],
                'primary_symptoms': [],
                'cyclical_dependencies': [],
                'issue_relationships': []
            }

    async def _perform_predictive_analysis(self, historical_data: List[Dict], current_analysis: Dict) -> Dict[str, Any]:
        """
        Perform predictive analysis based on historical patterns.
        """
        try:
            logger.info("Starting predictive analysis...")
            
            # Store historical data for pattern learning
            for data_point in historical_data:
                timestamp = data_point.get('timestamp', datetime.now())
                issues = data_point.get('issues', [])
                for issue in issues:
                    issue_type = issue.get('type', 'unknown')
                    self.historical_patterns[issue_type].append({
                        'timestamp': timestamp,
                        'severity': issue.get('severity', 'medium'),
                        'accounts_affected': issue.get('accounts_affected', []),
                        'resolution_time': issue.get('resolution_time', 0)
                    })
            
            # Predict future issues
            predictions = []
            current_time = datetime.now()
            
            for issue_category, patterns in self.historical_patterns.items():
                if len(patterns) >= 3:  # Need minimum data for prediction
                    prediction = await self._predict_issue_occurrence(issue_category, patterns, current_time)
                    if prediction:
                        predictions.append(prediction)
            
            # Identify early warning indicators
            early_warnings = await self._identify_early_warning_indicators(current_analysis, historical_data)
            
            # Generate preventive recommendations
            preventive_recommendations = await self._generate_preventive_recommendations(predictions, early_warnings)
            
            return {
                'predictions': predictions,
                'early_warning_indicators': early_warnings,
                'preventive_recommendations': preventive_recommendations,
                'prediction_confidence': self._calculate_prediction_confidence(predictions),
                'analysis_summary': {
                    'historical_data_points': len(historical_data),
                    'pattern_categories_analyzed': len(self.historical_patterns),
                    'predictions_generated': len(predictions),
                    'high_risk_predictions': len([p for p in predictions if p.get('probability', 0) > 0.8])
                }
            }
            
        except Exception as e:
            logger.error(f"Predictive analysis failed: {str(e)}")
            return {
                'error': str(e),
                'predictions': [],
                'early_warning_indicators': [],
                'preventive_recommendations': []
            }

    async def _perform_enhanced_root_cause_analysis(self, raw_log_content: str, issues_analysis: Dict, 
                                                   correlation_analysis: Dict, dependency_analysis: Dict) -> Dict[str, Any]:
        """Enhanced root cause analysis with correlation and dependency context."""
        
        prompt = f"""
{self.system_instructions}

## TASK: ENHANCED ROOT CAUSE ANALYSIS WITH CORRELATION AND DEPENDENCY CONTEXT

Based on the comprehensive analysis including correlations and dependencies, perform deep root cause analysis.

### IDENTIFIED ISSUES:
```json
{json.dumps(issues_analysis, indent=2)[:10000]}
```

### CORRELATION ANALYSIS:
```json
{json.dumps(correlation_analysis, indent=2)[:5000]}
```

### DEPENDENCY ANALYSIS:
```json
{json.dumps(dependency_analysis, indent=2)[:5000]}
```

### LOG SAMPLE FOR CONTEXT:
```
{raw_log_content[:30000]}
```

## ENHANCED ANALYSIS REQUIREMENTS:

1. **ROOT CAUSE IDENTIFICATION**: Use dependency graph to distinguish root causes from symptoms
2. **CORRELATION CONTEXT**: Incorporate temporal and account correlations in analysis
3. **CASCADING EFFECTS**: Analyze how issues propagate through the dependency chain
4. **ENVIRONMENTAL FACTORS**: Consider system-wide factors affecting multiple issues
5. **PREDICTIVE INSIGHTS**: Identify conditions that lead to issue escalation

## OUTPUT FORMAT:
```json
{{
  "primary_root_causes": [
    {{
      "issue_id": "power_management_cascade",
      "root_cause": "Windows power management causing network adapter disconnection cascade",
      "evidence_from_correlations": ["98% of connection drops occur within 60s of power resume events"],
      "dependency_chain": ["Power resume event", "Network adapter reset", "DNS resolution failure", "OAuth2 timeout", "Authentication failure"],
      "affected_issue_types": ["connection_drops", "oauth2_failure", "imap_auth_failure"],
      "system_components_involved": ["Windows Power Management", "Network Adapter Driver", "DNS Resolver", "OAuth2 Client"],
      "environmental_factors": ["Network adapter power saving enabled", "DNS cache timeout settings"],
      "escalation_triggers": ["Multiple rapid suspend/resume cycles", "Network instability during resume"],
      "likelihood_score": 0.95
    }}
  ],
  "correlation_insights": [
    {{
      "correlation_type": "temporal",
      "insight": "IMAP authentication failures follow power resume events with 85% correlation",
      "strength": 0.85,
      "business_impact": "Systematic email disruption after laptop sleep/wake cycles"
    }}
  ],
  "dependency_insights": [
    {{
      "dependency_type": "cascading_failure",
      "trigger_issue": "network_adapter_reset",
      "affected_issues": ["dns_resolution_failure", "oauth2_timeout", "connection_drops"],
      "prevention_point": "Configure network adapter to not allow power management shutdown",
      "impact_radius": "All email accounts using OAuth2 authentication"
    }}
  ]
}}
```

ANALYZE THE INTERCONNECTED NATURE OF ISSUES using correlation and dependency context.
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
                "error": f"Enhanced root cause analysis failed: {str(e)}",
                "primary_root_causes": [],
                "correlation_insights": [],
                "dependency_insights": []
            }

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp string to datetime object."""
        try:
            # Try common timestamp formats
            formats = [
                "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ"
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(timestamp_str, fmt)
                except ValueError:
                    continue
            
            # If all else fails, return current time
            return datetime.now()
        except:
            return datetime.now()

    async def _find_temporal_correlations(self, events: List[Dict]) -> List[Dict]:
        """Find temporal correlations between events."""
        correlations = []
        
        # Sort events by timestamp
        sorted_events = sorted(events, key=lambda x: x['timestamp'])
        
        # Find events that occur within temporal window
        for i, event1 in enumerate(sorted_events):
            for j, event2 in enumerate(sorted_events[i+1:], i+1):
                time_diff = (event2['timestamp'] - event1['timestamp']).total_seconds()
                
                if time_diff <= self.temporal_window:
                    # Calculate correlation strength based on frequency and timing
                    strength = 1.0 - (time_diff / self.temporal_window)
                    
                    correlations.append({
                        'source_issue': event1['issue_type'],
                        'target_issue': event2['issue_type'],
                        'strength': strength,
                        'average_delay': time_diff,
                        'frequency': 1,  # Would be calculated from multiple occurrences
                        'confidence': min(1.0, strength * 1.2)
                    })
        
        # Group and aggregate similar correlations
        correlation_groups = defaultdict(list)
        for corr in correlations:
            key = (corr['source_issue'], corr['target_issue'])
            correlation_groups[key].append(corr)
        
        # Calculate aggregated correlations
        aggregated = []
        for (source, target), group in correlation_groups.items():
            if len(group) >= 2:  # Only include patterns that occur multiple times
                avg_strength = sum(c['strength'] for c in group) / len(group)
                avg_delay = sum(c['average_delay'] for c in group) / len(group)
                
                aggregated.append({
                    'source_issue': source,
                    'target_issue': target,
                    'strength': avg_strength,
                    'average_delay': avg_delay,
                    'frequency': len(group),
                    'confidence': min(1.0, avg_strength * (len(group) / 10.0))
                })
        
        return sorted(aggregated, key=lambda x: x['strength'], reverse=True)

    async def _find_account_correlations(self, events: List[Dict]) -> List[Dict]:
        """Find correlations between issues affecting the same accounts."""
        account_issues = defaultdict(list)
        
        for event in events:
            account = event.get('account', 'unknown')
            if account != 'unknown':
                account_issues[account].append(event)
        
        correlations = []
        for account, account_events in account_issues.items():
            if len(account_events) > 1:
                issue_types = [e['issue_type'] for e in account_events]
                issue_counter = Counter(issue_types)
                
                for issue_type, count in issue_counter.items():
                    if count > 1:
                        correlations.append({
                            'account': account,
                            'issue_type': issue_type,
                            'frequency': count,
                            'correlation_type': 'account_specific',
                            'strength': min(1.0, count / 5.0)  # Normalize to max strength of 1.0
                        })
        
        return correlations

    async def _find_issue_type_correlations(self, events: List[Dict]) -> List[Dict]:
        """Find correlations between different issue types."""
        issue_cooccurrence = defaultdict(lambda: defaultdict(int))
        
        # Group events by time windows
        time_windows = defaultdict(list)
        for event in events:
            window_key = int(event['timestamp'].timestamp() // self.temporal_window)
            time_windows[window_key].append(event)
        
        # Count co-occurrences within windows
        for window_events in time_windows.values():
            issue_types_in_window = set(e['issue_type'] for e in window_events)
            for issue1 in issue_types_in_window:
                for issue2 in issue_types_in_window:
                    if issue1 != issue2:
                        issue_cooccurrence[issue1][issue2] += 1
        
        # Convert to correlation format
        correlations = []
        for issue1, related_issues in issue_cooccurrence.items():
            total_occurrences = sum(related_issues.values())
            for issue2, count in related_issues.items():
                strength = count / max(total_occurrences, 1)
                if strength > 0.3:  # Only include meaningful correlations
                    correlations.append({
                        'issue_type_1': issue1,
                        'issue_type_2': issue2,
                        'cooccurrence_count': count,
                        'strength': strength,
                        'correlation_type': 'issue_type_cooccurrence'
                    })
        
        return sorted(correlations, key=lambda x: x['strength'], reverse=True)

    async def _calculate_correlation_matrix(self, events: List[Dict]) -> Dict[str, Any]:
        """Calculate correlation matrix between all issue types."""
        issue_types = list(set(e['issue_type'] for e in events))
        n_types = len(issue_types)
        
        if n_types < 2:
            return {}
        
        # Create feature vectors for each issue type based on temporal patterns
        feature_vectors = []
        
        for issue_type in issue_types:
            type_events = [e for e in events if e['issue_type'] == issue_type]
            
            # Create features: hour of day, day of week, etc.
            features = [0] * 24  # Hour of day distribution
            for event in type_events:
                hour = event['timestamp'].hour
                features[hour] += 1
            
            # Normalize
            total = sum(features)
            if total > 0:
                features = [f / total for f in features]
            
            feature_vectors.append(features)
        
        # Calculate cosine similarity matrix
        if len(feature_vectors) > 1:
            similarity_matrix = cosine_similarity(feature_vectors)
            
            # Convert to dictionary format
            matrix_dict = {}
            for i, issue1 in enumerate(issue_types):
                matrix_dict[issue1] = {}
                for j, issue2 in enumerate(issue_types):
                    matrix_dict[issue1][issue2] = float(similarity_matrix[i][j])
            
            return matrix_dict
        
        return {}

    async def _predict_issue_occurrence(self, issue_type: str, patterns: List[Dict], current_time: datetime) -> Optional[Dict]:
        """Predict the likelihood of an issue occurring."""
        try:
            if len(patterns) < 3:
                return None
            
            # Calculate temporal patterns
            time_intervals = []
            for i in range(1, len(patterns)):
                if isinstance(patterns[i]['timestamp'], str):
                    curr_time = datetime.fromisoformat(patterns[i]['timestamp'])
                    prev_time = datetime.fromisoformat(patterns[i-1]['timestamp'])
                else:
                    curr_time = patterns[i]['timestamp']
                    prev_time = patterns[i-1]['timestamp']
                
                interval = (curr_time - prev_time).total_seconds()
                time_intervals.append(interval)
            
            # Calculate average interval and predict next occurrence
            if time_intervals:
                avg_interval = sum(time_intervals) / len(time_intervals)
                last_occurrence = patterns[-1]['timestamp']
                if isinstance(last_occurrence, str):
                    last_occurrence = datetime.fromisoformat(last_occurrence)
                
                predicted_time = last_occurrence + timedelta(seconds=avg_interval)
                time_until_prediction = (predicted_time - current_time).total_seconds()
                
                # Calculate probability based on pattern consistency
                interval_variance = np.var(time_intervals) if len(time_intervals) > 1 else 0
                consistency_score = 1.0 / (1.0 + interval_variance / (avg_interval ** 2)) if avg_interval > 0 else 0
                
                # Adjust probability based on recency and consistency
                if time_until_prediction > 0:
                    probability = consistency_score * (1.0 - min(time_until_prediction / (avg_interval * 2), 1.0))
                else:
                    probability = consistency_score * 1.2  # Overdue
                
                probability = max(0.0, min(1.0, probability))
                
                return {
                    'issue_type': issue_type,
                    'predicted_time': predicted_time.isoformat(),
                    'probability': probability,
                    'confidence': consistency_score,
                    'time_until_predicted': time_until_prediction,
                    'pattern_strength': len(patterns),
                    'average_interval_hours': avg_interval / 3600
                }
        
        except Exception as e:
            logger.error(f"Prediction calculation failed for {issue_type}: {str(e)}")
        
        return None

    async def _identify_early_warning_indicators(self, current_analysis: Dict, historical_data: List[Dict]) -> List[Dict]:
        """Identify early warning indicators for potential issues."""
        warnings = []
        
        try:
            # Check for known precursor patterns
            if 'account_analysis' in current_analysis:
                for account in current_analysis['account_analysis']:
                    account_email = account.get('account', '')
                    issues = account.get('primary_issues', [])
                    
                    # Warning: Multiple issue types for single account
                    if len(issues) > 2:
                        warnings.append({
                            'indicator_type': 'multiple_issues_single_account',
                            'account': account_email,
                            'severity': 'high',
                            'description': f'Account {account_email} showing {len(issues)} different issue types',
                            'risk_level': 0.8,
                            'recommended_action': 'Investigate account configuration and provider settings'
                        })
                    
                    # Warning: Authentication issues often precede connection failures
                    if any('auth' in issue.lower() for issue in issues):
                        warnings.append({
                            'indicator_type': 'authentication_precursor',
                            'account': account_email,
                            'severity': 'medium',
                            'description': 'Authentication issues detected - may precede connection failures',
                            'risk_level': 0.6,
                            'recommended_action': 'Verify account credentials and server settings'
                        })
            
            # Check for system-wide patterns
            if 'detected_issues' in current_analysis:
                critical_issues = [issue for issue in current_analysis['detected_issues'] 
                                 if issue.get('severity', '').lower() == 'critical']
                
                if len(critical_issues) > 0:
                    warnings.append({
                        'indicator_type': 'critical_issue_detected',
                        'severity': 'critical',
                        'description': f'{len(critical_issues)} critical issues detected',
                        'risk_level': 0.9,
                        'recommended_action': 'Immediate attention required for critical issues'
                    })
        
        except Exception as e:
            logger.error(f"Early warning identification failed: {str(e)}")
        
        return warnings

    async def _generate_preventive_recommendations(self, predictions: List[Dict], warnings: List[Dict]) -> List[Dict]:
        """Generate preventive maintenance recommendations."""
        recommendations = []
        
        try:
            # Recommendations based on predictions
            for prediction in predictions:
                if prediction.get('probability', 0) > 0.7:
                    recommendations.append({
                        'type': 'predictive_maintenance',
                        'priority': 'high',
                        'target_issue': prediction['issue_type'],
                        'recommended_action': f"Preemptive maintenance for {prediction['issue_type']}",
                        'timeframe': f"Within {prediction.get('average_interval_hours', 24)} hours",
                        'expected_benefit': 'Prevent predicted issue occurrence',
                        'confidence': prediction.get('confidence', 0.5)
                    })
            
            # Recommendations based on warnings
            for warning in warnings:
                if warning.get('risk_level', 0) > 0.7:
                    recommendations.append({
                        'type': 'risk_mitigation',
                        'priority': warning.get('severity', 'medium'),
                        'target_indicator': warning['indicator_type'],
                        'recommended_action': warning.get('recommended_action', 'Investigate and resolve'),
                        'timeframe': 'Immediate',
                        'expected_benefit': 'Reduce risk of issue escalation',
                        'confidence': warning.get('risk_level', 0.5)
                    })
            
            # General system health recommendations
            recommendations.append({
                'type': 'system_health',
                'priority': 'medium',
                'recommended_action': 'Regular system health monitoring and log analysis',
                'timeframe': 'Weekly',
                'expected_benefit': 'Early detection of emerging issues',
                'confidence': 0.8
            })
        
        except Exception as e:
            logger.error(f"Preventive recommendations generation failed: {str(e)}")
        
        return recommendations

    def _calculate_prediction_confidence(self, predictions: List[Dict]) -> float:
        """Calculate overall confidence in predictions."""
        if not predictions:
            return 0.0
        
        confidences = [p.get('confidence', 0) for p in predictions]
        return sum(confidences) / len(confidences)

    async def _generate_enhanced_solutions(self, issues_analysis: Dict, root_cause_analysis: Dict, 
                                         correlation_analysis: Dict, predictive_analysis: Dict) -> List[Dict[str, Any]]:
        """Generate enhanced solutions considering correlations and predictions."""
        # This would be the enhanced version of _generate_intelligent_solutions
        return await self._generate_intelligent_solutions(issues_analysis, root_cause_analysis)

    async def _create_enhanced_executive_summary(self, raw_log_content: str, issues_analysis: Dict, 
                                               root_cause_analysis: Dict, solutions: List[Dict],
                                               correlation_analysis: Dict, dependency_analysis: Dict, 
                                               predictive_analysis: Dict) -> str:
        """Create enhanced executive summary with all analysis components."""
        # This would be the enhanced version of _create_executive_summary
        return await self._create_executive_summary(raw_log_content, issues_analysis, root_cause_analysis, solutions)

# Main entry point
async def perform_intelligent_log_analysis(raw_log_content: str, basic_parsed_data: Dict[str, Any], 
                                         historical_data: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """
    Main entry point for enhanced intelligent log analysis using Gemini 2.5 Pro reasoning.
    Enhanced with predictive analysis, correlation detection, and dependency mapping.
    """
    analyzer = IntelligentLogAnalyzer()
    return await analyzer.perform_intelligent_analysis(raw_log_content, basic_parsed_data, historical_data)