"""
Advanced Solution Generation Engine for Mailbird Log Analysis
Provides detailed, actionable solutions with priority-based recommendations and account-specific guidance.
"""

import asyncio
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

# Import search tools for enhanced solutions
from app.agents_v2.primary_agent.tools import tavily_web_search


class DetailedSolutionStep(BaseModel):
    """Enhanced solution step with implementation details."""
    step_number: int
    description: str
    expected_outcome: str
    troubleshooting_note: Optional[str] = None
    estimated_time_minutes: Optional[int] = None
    risk_level: str = "Low"  # Low, Medium, High
    requires_restart: bool = False
    account_specific: bool = False
    specific_settings: Optional[Dict[str, str]] = None


class AccountSpecificSolution(BaseModel):
    """Complete solution tailored to specific account and issue type."""
    issue_id: str
    affected_accounts: List[str]
    solution_summary: str
    confidence_level: str  # High, Medium, Low
    priority: str  # Critical, High, Medium, Low
    solution_steps: List[DetailedSolutionStep]
    prerequisites: List[str]
    estimated_total_time_minutes: int
    success_probability: str
    alternative_approaches: List[str]
    references: List[str]
    requires_web_search: bool = False
    implementation_timeline: str  # "Immediate", "Day 1", "Week 1", etc.
    expected_outcome: str


class AdvancedSolutionEngine:
    """Advanced solution generation with account-specific analysis and detailed guidance."""
    
    def __init__(self):
        self.primary_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            temperature=0.1,
            google_api_key=os.getenv("GEMINI_API_KEY"),
        )
        
        # Account-specific solution templates
        self.solution_templates = {
            'imap_push_failure': {
                'priority': 'Critical',
                'timeline': 'Day 1',
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Disable IMAP push notifications for affected accounts',
                        'expected_outcome': 'Eliminates push listener failures',
                        'specific_settings': {'setting': 'Account Settings > Advanced > Disable Push Notifications'},
                        'estimated_time_minutes': 5
                    },
                    {
                        'step_number': 2,
                        'description': 'Configure polling interval to 5-10 minutes',
                        'expected_outcome': 'Stable connection with controlled polling',
                        'specific_settings': {'setting': 'Check for mail every 5 minutes'},
                        'estimated_time_minutes': 3
                    }
                ]
            },
            
            'smtp_send_failure': {
                'priority': 'Critical',
                'timeline': 'Immediate',
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Verify SMTP server settings',
                        'expected_outcome': 'Correct server configuration confirmed',
                        'troubleshooting_note': 'Check with email provider for correct settings',
                        'estimated_time_minutes': 10
                    },
                    {
                        'step_number': 2,
                        'description': 'Change encryption from SSL to TLS (port 587)',
                        'expected_outcome': 'Resolves SSL handshake failures',
                        'specific_settings': {
                            'server': 'Use TLS encryption',
                            'port': '587',
                            'auth': 'Use authentication'
                        },
                        'estimated_time_minutes': 5
                    }
                ]
            },
            
            'message_size_violation': {
                'priority': 'High',
                'timeline': 'Day 1',
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Enable large file handling in Mailbird settings',
                        'expected_outcome': 'Automatic compression for large attachments',
                        'specific_settings': {'setting': 'Settings > Composing > Large File Handling'},
                        'estimated_time_minutes': 3
                    },
                    {
                        'step_number': 2,
                        'description': 'Configure attachment size limits (Gmail: 25MB, Outlook: 20MB)',
                        'expected_outcome': 'Prevention of size limit violations',
                        'troubleshooting_note': 'Use cloud sharing for files exceeding limits',
                        'estimated_time_minutes': 5
                    }
                ]
            },
            
            'imap_auth_failure': {
                'priority': 'High',
                'timeline': 'Day 1',
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Verify IMAP server settings and credentials',
                        'expected_outcome': 'Correct authentication configuration',
                        'account_specific': True,
                        'estimated_time_minutes': 10
                    },
                    {
                        'step_number': 2,
                        'description': 'Generate app-specific password if available',
                        'expected_outcome': 'Bypasses 2FA authentication issues',
                        'troubleshooting_note': 'Required for accounts with 2FA enabled',
                        'estimated_time_minutes': 15
                    }
                ]
            },
            
            'oauth2_failure': {
                'priority': 'Medium',
                'timeline': 'Day 1',
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Configure reliable DNS servers (8.8.8.8, 1.1.1.1)',
                        'expected_outcome': 'Resolves DNS resolution issues for OAuth endpoints',
                        'specific_settings': {'dns_primary': '8.8.8.8', 'dns_secondary': '1.1.1.1'},
                        'estimated_time_minutes': 10
                    },
                    {
                        'step_number': 2,
                        'description': 'Re-authenticate affected Google/Microsoft accounts',
                        'expected_outcome': 'Fresh OAuth2 tokens obtained',
                        'account_specific': True,
                        'estimated_time_minutes': 10
                    }
                ]
            },
            
            'power_management_issues': {
                'priority': 'Medium',
                'timeline': 'Day 2',
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Disable network adapter power saving',
                        'expected_outcome': 'Prevents connection drops during system resume',
                        'specific_settings': {
                            'location': 'Device Manager > Network Adapters > Properties > Power Management',
                            'setting': 'Uncheck "Allow computer to turn off this device"'
                        },
                        'estimated_time_minutes': 5
                    },
                    {
                        'step_number': 2,
                        'description': 'Enable "Keep connections alive during sleep" in Mailbird',
                        'expected_outcome': 'Maintains connections during power state changes',
                        'specific_settings': {'setting': 'Settings > Advanced > Connection > Keep Alive'},
                        'estimated_time_minutes': 3
                    }
                ]
            },
            
            'connection_drops': {
                'priority': 'High',
                'timeline': 'Day 1',
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Configure firewall exceptions for email ports',
                        'expected_outcome': 'Eliminates firewall-related connection drops',
                        'specific_settings': {
                            'ports': '993 (IMAP SSL), 587 (SMTP), 443 (HTTPS)',
                            'application': 'Add Mailbird.exe to trusted applications'
                        },
                        'estimated_time_minutes': 15
                    },
                    {
                        'step_number': 2,
                        'description': 'Increase IMAP timeout settings',
                        'expected_outcome': 'Reduces timeout-related disconnections',
                        'specific_settings': {'timeout': '60 seconds'},
                        'estimated_time_minutes': 5
                    }
                ]
            }
        }

    async def generate_comprehensive_solutions(self, detected_issues: List[Dict[str, Any]], system_metadata: Dict[str, Any], account_analysis: List[Dict] = None) -> List[AccountSpecificSolution]:
        """Generate detailed, account-specific solutions for all detected issues."""
        solutions = []
        
        for issue in detected_issues:
            try:
                solution = await self._generate_account_specific_solution(issue, system_metadata, account_analysis)
                solutions.append(solution)
            except Exception as e:
                print(f"Failed to generate solution for issue {issue.get('issue_id', 'unknown')}: {e}")
                # Generate fallback solution
                fallback = self._generate_fallback_solution(issue)
                solutions.append(fallback)
        
        # Sort by priority and severity
        return sorted(solutions, key=lambda x: self._get_priority_score(x.priority), reverse=True)

    async def _generate_account_specific_solution(self, issue: Dict[str, Any], system_metadata: Dict[str, Any], account_analysis: List[Dict] = None) -> AccountSpecificSolution:
        """Generate detailed solution for specific issue with account context."""
        issue_type = issue.get('category', '').lower().replace(' ', '_')
        
        # Get base template
        template = self.solution_templates.get(issue_type)
        if not template:
            # Generate custom solution using LLM
            return await self._generate_llm_solution(issue, system_metadata)
        
        # Customize solution for specific accounts
        affected_accounts = issue.get('affected_accounts', [])
        solution_steps = []
        
        for base_step in template['base_steps']:
            step = DetailedSolutionStep(
                step_number=base_step['step_number'],
                description=self._customize_step_for_accounts(base_step['description'], affected_accounts),
                expected_outcome=base_step['expected_outcome'],
                troubleshooting_note=base_step.get('troubleshooting_note'),
                estimated_time_minutes=base_step.get('estimated_time_minutes', 10),
                risk_level=base_step.get('risk_level', 'Low'),
                account_specific=base_step.get('account_specific', False),
                specific_settings=base_step.get('specific_settings')
            )
            solution_steps.append(step)
        
        # Add account-specific steps
        if affected_accounts:
            account_specific_steps = self._generate_account_specific_steps(issue_type, affected_accounts)
            solution_steps.extend(account_specific_steps)
        
        # Generate detailed solution summary
        solution_summary = self._generate_solution_summary(issue, template, affected_accounts)
        
        # Calculate total time
        total_time = sum(step.estimated_time_minutes or 10 for step in solution_steps)
        
        return AccountSpecificSolution(
            issue_id=issue.get('issue_id', 'unknown'),
            affected_accounts=affected_accounts,
            solution_summary=solution_summary,
            confidence_level=self._determine_confidence(issue_type, system_metadata),
            priority=template['priority'],
            solution_steps=solution_steps,
            prerequisites=self._generate_prerequisites(issue_type, system_metadata),
            estimated_total_time_minutes=total_time,
            success_probability=self._calculate_success_probability(issue_type, system_metadata),
            alternative_approaches=self._generate_alternatives(issue_type),
            references=self._generate_references(issue_type),
            implementation_timeline=template['timeline'],
            expected_outcome=self._generate_expected_outcome(issue, template)
        )

    def _customize_step_for_accounts(self, description: str, accounts: List[str]) -> str:
        """Customize step description with specific account information."""
        if not accounts:
            return description
        
        if len(accounts) == 1:
            return f"{description} for {accounts[0]}"
        elif len(accounts) <= 3:
            return f"{description} for accounts: {', '.join(accounts)}"
        else:
            return f"{description} for {len(accounts)} affected accounts"

    def _generate_account_specific_steps(self, issue_type: str, accounts: List[str]) -> List[DetailedSolutionStep]:
        """Generate additional steps specific to affected accounts."""
        steps = []
        
        if issue_type == 'smtp_send_failure':
            for i, account in enumerate(accounts[:3], len(self.solution_templates[issue_type]['base_steps']) + 1):
                if '@gmail.com' in account:
                    steps.append(DetailedSolutionStep(
                        step_number=i,
                        description=f"For {account}: Verify Gmail SMTP settings (smtp.gmail.com:587, TLS)",
                        expected_outcome="Gmail-specific SMTP configuration confirmed",
                        specific_settings={'server': 'smtp.gmail.com', 'port': '587', 'encryption': 'TLS'},
                        estimated_time_minutes=5,
                        account_specific=True
                    ))
                elif '@outlook.com' in account or '@hotmail.com' in account:
                    steps.append(DetailedSolutionStep(
                        step_number=i,
                        description=f"For {account}: Verify Outlook SMTP settings (smtp-mail.outlook.com:587, TLS)",
                        expected_outcome="Outlook-specific SMTP configuration confirmed",
                        specific_settings={'server': 'smtp-mail.outlook.com', 'port': '587', 'encryption': 'TLS'},
                        estimated_time_minutes=5,
                        account_specific=True
                    ))
        
        return steps

    def _generate_solution_summary(self, issue: Dict, template: Dict, accounts: List[str]) -> str:
        """Generate comprehensive solution summary."""
        issue_category = issue.get('category', 'Unknown issue')
        severity = issue.get('severity', 'Medium')
        
        account_info = f"affecting {len(accounts)} accounts" if accounts else "system-wide"
        
        return f"Resolve {issue_category} ({severity} priority) {account_info} through targeted configuration changes and optimization"

    def _determine_confidence(self, issue_type: str, system_metadata: Dict) -> str:
        """Determine confidence level based on issue type and system context."""
        # Well-known issues have high confidence
        known_issues = ['smtp_send_failure', 'imap_push_failure', 'message_size_violation']
        
        if issue_type in known_issues:
            return "High"
        elif issue_type in self.solution_templates:
            return "Medium"
        else:
            return "Low"

    def _calculate_success_probability(self, issue_type: str, system_metadata: Dict) -> str:
        """Calculate success probability based on issue complexity."""
        simple_fixes = ['message_size_violation', 'power_management_issues']
        complex_fixes = ['smtp_send_failure', 'oauth2_failure']
        
        if issue_type in simple_fixes:
            return "High"
        elif issue_type in complex_fixes:
            return "Medium"
        else:
            return "Medium"

    def _generate_prerequisites(self, issue_type: str, system_metadata: Dict) -> List[str]:
        """Generate prerequisites based on issue type."""
        common_prereqs = ["Administrative access to Windows system", "Mailbird application access"]
        
        specific_prereqs = {
            'smtp_send_failure': ["Email provider SMTP settings", "Account credentials"],
            'oauth2_failure': ["Internet connectivity", "DNS access"],
            'power_management_issues': ["Device Manager access"],
            'connection_drops': ["Firewall configuration access"]
        }
        
        return common_prereqs + specific_prereqs.get(issue_type, [])

    def _generate_alternatives(self, issue_type: str) -> List[str]:
        """Generate alternative approaches."""
        alternatives = {
            'smtp_send_failure': [
                "Use webmail interface as temporary workaround",
                "Configure backup SMTP server",
                "Contact email provider support"
            ],
            'imap_push_failure': [
                "Switch to POP3 if supported",
                "Use manual refresh instead of push",
                "Configure longer polling intervals"
            ],
            'message_size_violation': [
                "Use cloud file sharing services",
                "Compress attachments before sending",
                "Split large emails into multiple messages"
            ],
            'oauth2_failure': [
                "Use app-specific passwords",
                "Configure manual authentication",
                "Contact provider technical support"
            ]
        }
        
        return alternatives.get(issue_type, ["Contact Mailbird support", "Check provider documentation"])

    def _generate_references(self, issue_type: str) -> List[str]:
        """Generate relevant documentation references."""
        references = {
            'smtp_send_failure': [
                "https://support.mailbird.com/hc/en-us/articles/115001524969-SMTP-Settings",
                "https://support.google.com/mail/answer/7126229?hl=en"
            ],
            'imap_push_failure': [
                "https://support.mailbird.com/hc/en-us/articles/213741985-IMAP-Settings",
                "https://support.mailbird.com/hc/en-us/articles/360000373434-Push-Notifications"
            ],
            'oauth2_failure': [
                "https://support.google.com/accounts/answer/185833",
                "https://support.microsoft.com/en-us/account-billing/using-app-passwords-with-apps-that-don-t-support-two-step-verification-5896ed9b-4263-e681-128a-a6f2979a7944"
            ]
        }
        
        return references.get(issue_type, ["https://support.mailbird.com"])

    def _generate_expected_outcome(self, issue: Dict, template: Dict) -> str:
        """Generate detailed expected outcome."""
        severity = issue.get('severity', 'Medium')
        occurrences = issue.get('occurrences', 1)
        
        if severity == 'Critical':
            return f"Complete resolution of critical issue, eliminating all {occurrences} occurrences and restoring full functionality"
        elif severity == 'High':
            return f"90% reduction in issue frequency, improved stability for affected accounts"
        else:
            return f"Significant improvement in system stability, reduced occurrence frequency"

    def _get_priority_score(self, priority: str) -> int:
        """Convert priority to numeric score for sorting."""
        scores = {'Critical': 4, 'High': 3, 'Medium': 2, 'Low': 1}
        return scores.get(priority, 0)

    async def _generate_llm_solution(self, issue: Dict, system_metadata: Dict) -> AccountSpecificSolution:
        """Generate custom solution using LLM for unknown issue types."""
        # This would use the existing LLM-based solution generation
        # For now, return a basic fallback
        return self._generate_fallback_solution(issue)

    def _generate_fallback_solution(self, issue: Dict) -> AccountSpecificSolution:
        """Generate basic fallback solution."""
        return AccountSpecificSolution(
            issue_id=issue.get('issue_id', 'unknown'),
            affected_accounts=issue.get('affected_accounts', []),
            solution_summary="General troubleshooting approach for unrecognized issue",
            confidence_level="Low",
            priority="Medium",
            solution_steps=[
                DetailedSolutionStep(
                    step_number=1,
                    description="Restart Mailbird application completely",
                    expected_outcome="Fresh application state",
                    estimated_time_minutes=2
                ),
                DetailedSolutionStep(
                    step_number=2,
                    description="Check Windows Event Viewer for additional details",
                    expected_outcome="Additional diagnostic information",
                    estimated_time_minutes=10
                ),
                DetailedSolutionStep(
                    step_number=3,
                    description="Contact Mailbird support with log details",
                    expected_outcome="Professional assistance",
                    estimated_time_minutes=15
                )
            ],
            prerequisites=["Administrative access"],
            estimated_total_time_minutes=27,
            success_probability="Medium",
            alternative_approaches=["Contact technical support"],
            references=["https://support.mailbird.com"],
            implementation_timeline="Day 1",
            expected_outcome="Basic troubleshooting completed, issue escalated if unresolved"
        )


# Main entry point
async def generate_comprehensive_solutions(detected_issues: List[Dict[str, Any]], system_metadata: Dict[str, Any], account_analysis: List[Dict] = None) -> List[AccountSpecificSolution]:
    """Generate comprehensive solutions for all detected issues."""
    engine = AdvancedSolutionEngine()
    return await engine.generate_comprehensive_solutions(detected_issues, system_metadata, account_analysis)