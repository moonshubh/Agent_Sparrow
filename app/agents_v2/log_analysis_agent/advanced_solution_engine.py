"""
Advanced Solution Generation Engine for Mailbird Log Analysis
Provides detailed, actionable solutions with priority-based recommendations and account-specific guidance.
"""

import asyncio
import json
import subprocess
import platform
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import os
import re
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.settings import settings
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

# Import search tools for enhanced solutions
from app.agents_v2.primary_agent.tools import tavily_web_search

logger = logging.getLogger(__name__)

# Precompiled command patterns
SAFE_COMMAND_PATTERNS = [
    re.compile(r'^reg query.*$', re.IGNORECASE),
    re.compile(r'^powershell -Command "Get-Process.*"$', re.IGNORECASE),
    re.compile(r'^systemctl status.*$', re.IGNORECASE),
    re.compile(r'^ls -la.*$', re.IGNORECASE),
    re.compile(r'^stat .*$', re.IGNORECASE),
    re.compile(r'^echo \$.*$', re.IGNORECASE),
    re.compile(r'^security find-.*$', re.IGNORECASE),
]

DANGEROUS_COMMAND_PATTERNS = [
    re.compile(r'.*rm -rf.*', re.IGNORECASE),
    re.compile(r'.*del /f.*', re.IGNORECASE),
    re.compile(r'.*format.*', re.IGNORECASE),
    re.compile(r'.*shutdown.*', re.IGNORECASE),
    re.compile(r'.*reboot.*', re.IGNORECASE),
    re.compile(r'.*mkfs.*', re.IGNORECASE),
]


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
    platform_specific: Optional[str] = None  # windows, macos, linux
    automated_script: Optional[str] = None  # Script for automated execution
    validation_command: Optional[str] = None  # Command to validate step completion
    rollback_procedure: Optional[str] = None  # How to undo this step if needed


class ValidationResult(BaseModel):
    """Result of solution validation."""
    step_number: int
    is_successful: bool
    validation_output: str
    error_message: Optional[str] = None
    requires_manual_verification: bool = False

class AutomatedTest(BaseModel):
    """Automated test for solution validation."""
    test_id: str
    test_name: str
    test_script: str
    expected_result: str
    platform_requirements: List[str]
    timeout_seconds: int = 30

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
    platform_compatibility: List[str] = ["windows", "macos", "linux"]
    automated_tests: List[AutomatedTest] = []
    remediation_script: Optional[str] = None  # Complete remediation script
    rollback_script: Optional[str] = None  # Complete rollback script
    success_criteria: List[str] = []  # How to verify solution worked


class AdvancedSolutionEngine:
    """Advanced solution generation with account-specific analysis and detailed guidance."""
    
    def __init__(self):
        self.primary_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            temperature=0.1,
            google_api_key=settings.gemini_api_key,
        )
        
        # Platform detection
        self.current_platform = self._detect_platform()
        
        # Solution validation tracking
        self.validation_history = {}
        self.effectiveness_file = os.path.join(os.path.dirname(__file__), "solution_effectiveness_data.json")
        self.solution_effectiveness = {}
        self._load_effectiveness_data()
        
        # Platform-specific solution templates
        self.platform_solutions = {
            'windows': self._get_windows_solutions(),
            'macos': self._get_macos_solutions(),
            'linux': self._get_linux_solutions()
        }
        
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
                        'specific_settings': {'setting': 'Settings > Advanced > Sync behavior > Download messages on demand'},
                        'estimated_time_minutes': 5
                    },
                    {
                        'step_number': 2,
                        'description': 'Configure polling interval to 5-10 minutes',
                        'expected_outcome': 'Stable connection with controlled polling',
                        'specific_settings': {'setting': 'Manual email check - no automatic interval setting available'},
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
                        'specific_settings': {'setting': 'Settings > Advanced > Sync behavior > Attachment auto-download limit'},
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
        try:
            # Get Mailbird settings context - import here to avoid circular dependency
            from .mailbird_settings_knowledge import get_mailbird_settings_context
            mailbird_settings_context = get_mailbird_settings_context()
            
            # Create detailed prompt for solution generation
            prompt = f"""
You are a Mailbird technical specialist. Generate a comprehensive solution for this issue.

{mailbird_settings_context}

ISSUE DETAILS:
- Category: {issue.get('category', 'Unknown')}
- Severity: {issue.get('severity', 'Medium')}
- Description: {issue.get('description', 'Unknown issue')}
- Root Cause: {issue.get('root_cause', 'Unknown')}
- Affected Accounts: {issue.get('affected_accounts', [])}

SYSTEM CONTEXT:
- Mailbird Version: {system_metadata.get('mailbird_version', 'Unknown')}
- OS: {system_metadata.get('os_version', 'Windows')}
- Account Count: {system_metadata.get('account_count', 0)}

Provide a JSON response with:
{{
  "solution_summary": "Brief summary of the solution",
  "confidence_level": "High/Medium/Low",
  "priority": "Critical/High/Medium/Low",
  "steps": [
    {{
      "step_number": 1,
      "description": "Step description - ONLY use settings from the Valid Mailbird Settings Reference",
      "expected_outcome": "What should happen",
      "estimated_time_minutes": 5
    }}
  ],
  "estimated_total_time_minutes": 30
}}

IMPORTANT: Only recommend settings that exist in the Valid Mailbird Settings Reference above.
"""
            
            response = await self.primary_llm.ainvoke(prompt)
            solution_data = json.loads(response.content)
            
            # Convert to AccountSpecificSolution
            solution_steps = []
            for step in solution_data.get('steps', []):
                solution_steps.append(DetailedSolutionStep(
                    step_number=step['step_number'],
                    description=step['description'],
                    expected_outcome=step['expected_outcome'],
                    estimated_time_minutes=step.get('estimated_time_minutes', 5),
                    risk_level=step.get('risk_level', 'Low')
                ))
            
            return AccountSpecificSolution(
                issue_id=issue.get('issue_id', 'unknown'),
                affected_accounts=issue.get('affected_accounts', []),
                solution_summary=solution_data.get('solution_summary', 'Custom solution generated'),
                confidence_level=solution_data.get('confidence_level', 'Medium'),
                priority=solution_data.get('priority', 'Medium'),
                solution_steps=solution_steps,
                estimated_total_time_minutes=solution_data.get('estimated_total_time_minutes', 30)
            )
            
        except Exception as e:
            print(f"LLM solution generation failed: {e}")
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


    def _detect_platform(self) -> str:
        """Detect the current platform."""
        system = platform.system().lower()
        if system == 'darwin':
            return 'macos'
        elif system == 'windows':
            return 'windows'
        elif system == 'linux':
            return 'linux'
        else:
            return 'unknown'

    def _get_windows_solutions(self) -> Dict[str, Dict]:
        """Get Windows-specific solutions."""
        return {
            'registry_access_failure': {
                'priority': 'High',
                'timeline': 'Immediate',
                'platform_compatibility': ['windows'],
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Run Mailbird as Administrator',
                        'expected_outcome': 'Elevated permissions for registry access',
                        'platform_specific': 'windows',
                        'automated_script': 'powershell -Command "Start-Process mailbird.exe -Verb RunAs"',
                        'validation_command': 'powershell -Command "Get-Process mailbird | Select-Object ProcessName,Id"',
                        'estimated_time_minutes': 2
                    },
                    {
                        'step_number': 2,
                        'description': 'Check registry permissions for HKEY_CURRENT_USER\\Software\\Mailbird',
                        'expected_outcome': 'Registry access permissions verified',
                        'platform_specific': 'windows',
                        'automated_script': 'reg query "HKEY_CURRENT_USER\\Software\\Mailbird" /s',
                        'rollback_procedure': 'No changes made, safe to continue',
                        'safety_note': 'Registry queries are generally safe but review system configuration carefully before proceeding.',
                        'estimated_time_minutes': 3
                    }
                ]
            },
            'com_activation_failure': {
                'priority': 'Medium',
                'timeline': 'Day 1',
                'platform_compatibility': ['windows'],
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Re-register Mailbird COM components',
                        'expected_outcome': 'COM components properly registered',
                        'platform_specific': 'windows',
                        'automated_script': 'regsvr32 /s "C:\\Program Files\\Mailbird\\mailbird.dll"',
                        'validation_command': 'reg query "HKEY_CLASSES_ROOT\\Mailbird" /f "Mailbird"',
                        'estimated_time_minutes': 5
                    }
                ]
            }
        }

    def _get_macos_solutions(self) -> Dict[str, Dict]:
        """Get macOS-specific solutions."""
        return {
            'keychain_access_failure': {
                'priority': 'High',
                'timeline': 'Immediate',
                'platform_compatibility': ['macos'],
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Reset Keychain access for Mailbird',
                        'expected_outcome': 'Mailbird can access stored credentials',
                        'platform_specific': 'macos',
                        'automated_script': 'security delete-generic-password -s "Mailbird"',
                        'validation_command': 'security find-generic-password -s "Mailbird"',
                        'rollback_procedure': 'Re-add credentials manually if needed',
                        'estimated_time_minutes': 5
                    },
                    {
                        'step_number': 2,
                        'description': 'Grant Mailbird access to Keychain',
                        'expected_outcome': 'Keychain access permissions restored',
                        'platform_specific': 'macos',
                        'troubleshooting_note': 'May require manual authorization in Keychain Access app',
                        'estimated_time_minutes': 3
                    }
                ]
            },
            'sandbox_violation': {
                'priority': 'Critical',
                'timeline': 'Immediate',
                'platform_compatibility': ['macos'],
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Check and update Mailbird permissions in System Preferences',
                        'expected_outcome': 'Full disk access and file permissions granted',
                        'platform_specific': 'macos',
                        'troubleshooting_note': 'Go to System Preferences > Security & Privacy > Privacy tab',
                        'estimated_time_minutes': 5
                    }
                ]
            }
        }

    def _get_linux_solutions(self) -> Dict[str, Dict]:
        """Get Linux-specific solutions."""
        return {
            'dbus_connection_failure': {
                'priority': 'Medium',
                'timeline': 'Day 1',
                'platform_compatibility': ['linux'],
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Restart D-Bus service',
                        'expected_outcome': 'D-Bus communication restored',
                        'platform_specific': 'linux',
                        'automated_script': 'if [ $(id -u) -eq 0 ]; then systemctl restart dbus; else echo "Requires root privileges to restart dbus"; fi',
                        'validation_command': 'systemctl status dbus',
                        'estimated_time_minutes': 2
                    },
                    {
                        'step_number': 2,
                        'description': 'Check D-Bus session for user',
                        'expected_outcome': 'User D-Bus session is active',
                        'platform_specific': 'linux',
                        'automated_script': 'dbus-launch --exit-with-session',
                        'validation_command': 'echo $DBUS_SESSION_BUS_ADDRESS',
                        'estimated_time_minutes': 3
                    }
                ]
            },
            'permission_denied': {
                'priority': 'High',
                'timeline': 'Immediate',
                'platform_compatibility': ['linux'],
                'base_steps': [
                    {
                        'step_number': 1,
                        'description': 'Check file permissions for Mailbird directory',
                        'expected_outcome': 'Correct file permissions verified',
                        'platform_specific': 'linux',
                        'automated_script': 'ls -la ~/.mailbird',
                        'validation_command': 'stat ~/.mailbird',
                        'estimated_time_minutes': 2
                    },
                    {
                        'step_number': 2,
                        'description': 'Fix file permissions if needed',
                        'expected_outcome': 'File permissions corrected',
                        'platform_specific': 'linux',
                        'automated_script': 'chmod -R 755 ~/.mailbird',
                        'rollback_procedure': 'chmod -R 644 ~/.mailbird (if needed)',
                        'estimated_time_minutes': 1
                    }
                ]
            }
        }

    async def validate_solution_step(self, step: DetailedSolutionStep) -> ValidationResult:
        """Validate that a solution step was executed successfully."""
        try:
            if not step.validation_command:
                return ValidationResult(
                    step_number=step.step_number,
                    is_successful=True,
                    validation_output="No validation command provided",
                    requires_manual_verification=True
                )
            
            # Execute validation command
            result = await self._execute_command_safely(step.validation_command)
            
            # Determine success based on command output and expected outcome
            is_successful = self._evaluate_validation_result(result, step.expected_outcome)
            
            return ValidationResult(
                step_number=step.step_number,
                is_successful=is_successful,
                validation_output=result.get('output', ''),
                error_message=result.get('error') if not is_successful else None,
                requires_manual_verification=False
            )
            
        except Exception as e:
            logger.error(f"Validation failed for step {step.step_number}: {str(e)}")
            return ValidationResult(
                step_number=step.step_number,
                is_successful=False,
                validation_output="",
                error_message=str(e),
                requires_manual_verification=True
            )

    async def execute_automated_remediation(self, solution: AccountSpecificSolution) -> Dict[str, Any]:
        """Execute automated remediation for a solution."""
        try:
            logger.info(f"Starting automated remediation for {solution.issue_id}")
            
            execution_results = []
            overall_success = True
            
            for step in solution.solution_steps:
                if step.automated_script and step.platform_specific == self.current_platform:
                    logger.info(f"Executing step {step.step_number}: {step.description}")
                    
                    # Execute the automated script
                    execution_result = await self._execute_command_safely(step.automated_script)
                    
                    if execution_result.get('success', False):
                        # Validate the step
                        validation_result = await self.validate_solution_step(step)
                        execution_results.append({
                            'step_number': step.step_number,
                            'executed': True,
                            'execution_output': execution_result.get('output', ''),
                            'validation_result': validation_result.dict(),
                            'success': validation_result.is_successful
                        })
                        
                        if not validation_result.is_successful:
                            overall_success = False
                            logger.warning(f"Step {step.step_number} execution succeeded but validation failed")
                    else:
                        execution_results.append({
                            'step_number': step.step_number,
                            'executed': False,
                            'error': execution_result.get('error', 'Unknown error'),
                            'success': False
                        })
                        overall_success = False
                        logger.error(f"Step {step.step_number} execution failed")
                else:
                    execution_results.append({
                        'step_number': step.step_number,
                        'executed': False,
                        'reason': f'No automated script for platform {self.current_platform}',
                        'success': None
                    })
            
            # Run automated tests if available
            test_results = []
            if solution.automated_tests:
                for test in solution.automated_tests:
                    if self.current_platform in test.platform_requirements:
                        test_result = await self._run_automated_test(test)
                        test_results.append(test_result)
            
            return {
                'overall_success': overall_success,
                'execution_results': execution_results,
                'test_results': test_results,
                'remediation_completed': overall_success,
                'next_steps': self._generate_next_steps(overall_success, execution_results)
            }
            
        except Exception as e:
            logger.error(f"Automated remediation failed: {str(e)}")
            return {
                'overall_success': False,
                'error': str(e),
                'execution_results': [],
                'test_results': [],
                'remediation_completed': False
            }

    async def generate_remediation_script(self, solution: AccountSpecificSolution, target_platform: str) -> str:
        """Generate a complete remediation script for the specified platform."""
        try:
            if target_platform == 'windows':
                return await self._generate_windows_script(solution)
            elif target_platform == 'macos':
                return await self._generate_macos_script(solution)
            elif target_platform == 'linux':
                return await self._generate_linux_script(solution)
            else:
                return "# Unsupported platform"
        except Exception as e:
            logger.error(f"Script generation failed: {str(e)}")
            return f"# Error generating script: {str(e)}"

    async def learn_from_resolution(self, solution_id: str, execution_results: Dict[str, Any], 
                                   user_feedback: Optional[Dict] = None):
        """Learn from solution execution results to improve future recommendations."""
        try:
            overall_success = execution_results.get('overall_success', False)
            
            # Update solution effectiveness tracking
            if solution_id not in self.solution_effectiveness:
                self.solution_effectiveness[solution_id] = {
                    'total_attempts': 0,
                    'successful_attempts': 0,
                    'common_failures': [],
                    'user_feedback_scores': []
                }
            
            self.solution_effectiveness[solution_id]['total_attempts'] += 1
            
            if overall_success:
                self.solution_effectiveness[solution_id]['successful_attempts'] += 1
            else:
                # Analyze failure patterns
                failed_steps = [r for r in execution_results.get('execution_results', []) 
                              if not r.get('success', True)]
                for failure in failed_steps:
                    self.solution_effectiveness[solution_id]['common_failures'].append({
                        'step_number': failure.get('step_number'),
                        'error': failure.get('error', 'Unknown'),
                        'timestamp': datetime.now().isoformat()
                    })
            
            # Store user feedback if provided
            if user_feedback:
                self.solution_effectiveness[solution_id]['user_feedback_scores'].append({
                    'score': user_feedback.get('effectiveness_score', 0),
                    'comments': user_feedback.get('comments', ''),
                    'timestamp': datetime.now().isoformat()
                })
            
            logger.info(f"Learning data updated for solution {solution_id}")
            self._save_effectiveness_data()

        except Exception as e:
            logger.error(f"Learning from resolution failed: {str(e)}")

    async def _execute_command_safely(self, command: str) -> Dict[str, Any]:
        """SECURITY DISABLED: Command execution disabled for security reasons."""
        # CRITICAL SECURITY: Command execution has been permanently disabled
        # This prevents potential security vulnerabilities from arbitrary command execution
        
        return {
            'success': False,
            'error': 'SECURITY: Command execution disabled - automated remediation not available for safety',
            'output': 'Command execution has been disabled for security reasons. Manual execution required.',
            'command_suggested': command,
            'manual_execution_required': True
        }

    def _is_command_safe(self, command: str) -> bool:
        """Check if a command is safe to execute."""
        for pattern in DANGEROUS_COMMAND_PATTERNS:
            if pattern.match(command):
                return False

        for pattern in SAFE_COMMAND_PATTERNS:
            if pattern.match(command):
                return True

        basic_safe_commands = ['echo', 'ls', 'dir', 'cat', 'type', 'whoami']
        first_word = command.split()[0] if command.split() else ''
        return first_word in basic_safe_commands

    def _evaluate_validation_result(self, result: Dict[str, Any], expected_outcome: str) -> bool:
        """Evaluate if validation result indicates success."""
        if not result.get('success', False):
            return False
        
        output = result.get('output', '').lower()
        expected = expected_outcome.lower()
        
        # Simple heuristic - check if key terms from expected outcome appear in output
        key_terms = [word for word in expected.split() if len(word) > 3]
        
        if key_terms:
            matches = sum(1 for term in key_terms if term in output)
            return matches >= len(key_terms) // 2  # At least half the key terms should match
        
        return True  # If no specific terms to check, assume success

    def _load_effectiveness_data(self) -> None:
        """Load solution effectiveness data from disk."""
        if os.path.exists(self.effectiveness_file):
            try:
                with open(self.effectiveness_file, "r") as f:
                    self.solution_effectiveness = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load effectiveness data: {e}")
                self.solution_effectiveness = {}

    def _save_effectiveness_data(self) -> None:
        """Persist solution effectiveness data to disk."""
        try:
            with open(self.effectiveness_file, "w") as f:
                json.dump(self.solution_effectiveness, f)
        except Exception as e:
            logger.error(f"Failed to save effectiveness data: {e}")

    async def _run_automated_test(self, test: AutomatedTest) -> Dict[str, Any]:
        """Run an automated test and evaluate results."""
        try:
            result = await self._execute_command_safely(test.test_script)
            
            # Simple evaluation - check if expected result appears in output
            success = test.expected_result.lower() in result.get('output', '').lower()
            
            return {
                'test_id': test.test_id,
                'test_name': test.test_name,
                'executed': True,
                'success': success,
                'output': result.get('output', ''),
                'error': result.get('error') if not success else None
            }
            
        except Exception as e:
            return {
                'test_id': test.test_id,
                'test_name': test.test_name,
                'executed': False,
                'success': False,
                'error': str(e)
            }

    def _generate_next_steps(self, overall_success: bool, execution_results: List[Dict]) -> List[str]:
        """Generate next steps based on execution results."""
        if overall_success:
            return [
                "Monitor system for 24-48 hours to ensure issue resolution",
                "Test email functionality with affected accounts",
                "Document successful resolution for future reference"
            ]
        else:
            failed_steps = [r for r in execution_results if not r.get('success', True)]
            
            next_steps = ["Review failed automated steps:"]
            for failure in failed_steps:
                next_steps.append(f"- Manually execute step {failure.get('step_number', 'unknown')}")
            
            next_steps.extend([
                "Contact technical support if manual steps also fail",
                "Provide execution logs for further analysis"
            ])
            
            return next_steps

    async def _generate_windows_script(self, solution: AccountSpecificSolution) -> str:
        """Generate PowerShell script for Windows."""
        script_lines = [
            "# Mailbird Issue Resolution Script - Windows",
            f"# Generated for issue: {solution.issue_id}",
            f"# Priority: {solution.priority}",
            "",
            "# Check if running as administrator",
            "if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] \"Administrator\")) {",
            "    Write-Host \"This script requires administrator privileges. Please run as administrator.\" -ForegroundColor Red",
            "    exit 1",
            "}",
            "",
            "Write-Host \"Starting Mailbird issue resolution...\" -ForegroundColor Green",
            ""
        ]
        
        for step in solution.solution_steps:
            if step.platform_specific == 'windows' and step.automated_script:
                script_lines.extend([
                    f"# Step {step.step_number}: {step.description}",
                    f"Write-Host \"Executing: {step.description}\" -ForegroundColor Yellow",
                    step.automated_script,
                    ""
                ])
                
                if step.validation_command:
                    script_lines.extend([
                        f"# Validation for step {step.step_number}",
                        step.validation_command,
                        ""
                    ])
        
        script_lines.append("Write-Host \"Script execution completed.\" -ForegroundColor Green")
        
        return "\n".join(script_lines)

    async def _generate_macos_script(self, solution: AccountSpecificSolution) -> str:
        """Generate bash script for macOS."""
        script_lines = [
            "#!/bin/bash",
            "# Mailbird Issue Resolution Script - macOS",
            f"# Generated for issue: {solution.issue_id}",
            f"# Priority: {solution.priority}",
            "",
            "set -e  # Exit on any error",
            "",
            "echo \"Starting Mailbird issue resolution...\"",
            ""
        ]
        
        for step in solution.solution_steps:
            if step.platform_specific == 'macos' and step.automated_script:
                script_lines.extend([
                    f"# Step {step.step_number}: {step.description}",
                    f"echo \"Executing: {step.description}\"",
                    step.automated_script,
                    ""
                ])
                
                if step.validation_command:
                    script_lines.extend([
                        f"# Validation for step {step.step_number}",
                        step.validation_command,
                        ""
                    ])
        
        script_lines.append("echo \"Script execution completed.\"")
        
        return "\n".join(script_lines)

    async def _generate_linux_script(self, solution: AccountSpecificSolution) -> str:
        """Generate bash script for Linux."""
        script_lines = [
            "#!/bin/bash",
            "# Mailbird Issue Resolution Script - Linux", 
            f"# Generated for issue: {solution.issue_id}",
            f"# Priority: {solution.priority}",
            "",
            "set -e  # Exit on any error",
            "",
            "echo \"Starting Mailbird issue resolution...\"",
            ""
        ]
        
        for step in solution.solution_steps:
            if step.platform_specific == 'linux' and step.automated_script:
                script_lines.extend([
                    f"# Step {step.step_number}: {step.description}",
                    f"echo \"Executing: {step.description}\"",
                    step.automated_script,
                    ""
                ])
                
                if step.validation_command:
                    script_lines.extend([
                        f"# Validation for step {step.step_number}",
                        step.validation_command,
                        ""
                    ])
        
        script_lines.append("echo \"Script execution completed.\"")
        
        return "\n".join(script_lines)

# Main entry point
async def generate_comprehensive_solutions(detected_issues: List[Dict[str, Any]], system_metadata: Dict[str, Any], account_analysis: List[Dict] = None) -> List[AccountSpecificSolution]:
    """Generate comprehensive solutions for all detected issues."""
    engine = AdvancedSolutionEngine()
    return await engine.generate_comprehensive_solutions(detected_issues, system_metadata, account_analysis)