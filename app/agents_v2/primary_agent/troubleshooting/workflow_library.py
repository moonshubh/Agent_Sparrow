"""
Agent Sparrow - Troubleshooting Workflow Library

This module implements a comprehensive library of structured troubleshooting workflows
with progressive complexity handling and adaptive workflow selection.
"""

import logging
from typing import Dict, List, Optional, Any
import asyncio

from .troubleshooting_schemas import (
    TroubleshootingWorkflow,
    DiagnosticStep,
    DiagnosticStepType,
    TroubleshootingPhase,
    VerificationCheckpoint,
    EscalationCriteria,
    EscalationTrigger
)
from app.agents_v2.primary_agent.reasoning.schemas import ProblemCategory
from app.agents_v2.primary_agent.prompts.emotion_templates import EmotionalState

logger = logging.getLogger(__name__)


class WorkflowLibrary:
    """
    Comprehensive library of structured troubleshooting workflows
    
    Provides systematic workflow management through:
    - Pre-built workflows for common problem categories
    - Progressive complexity scaling (Level 1-5)
    - Adaptive workflow selection based on customer characteristics
    - Dynamic workflow modification for specific situations
    """
    
    def __init__(self, lazy_load: bool = False):
        """Initialize workflow library with pre-built workflows
        
        Args:
            lazy_load: If True, workflows will be loaded on first use instead of at initialization.
                     If False, all workflows are loaded immediately. Defaults to False.
        """
        self.workflows: Dict[str, TroubleshootingWorkflow] = {}
        self._lazy_load = lazy_load
        self._initialized = False
        
        # Initialize workflows immediately unless lazy loading is enabled
        if not self._lazy_load:
            self._initialize_all_workflows()
    
    def _initialize_all_workflows(self) -> None:
        """Initialize all workflow categories"""
        if self._initialized:
            return
            
        self._initialize_email_connectivity_workflows()
        self._initialize_account_setup_workflows()
        self._initialize_sync_issue_workflows()
        self._initialize_performance_workflows()
        self._initialize_feature_education_workflows()
        
        self._initialized = True
        logger.info(f"WorkflowLibrary initialized with {len(self.workflows)} troubleshooting workflows")
    
    async def get_workflows_for_category(
        self,
        problem_category: ProblemCategory,
        customer_emotion: EmotionalState = EmotionalState.NEUTRAL
    ) -> List[TroubleshootingWorkflow]:
        """
        Get appropriate workflows for problem category and customer state
        
        Args:
            problem_category: Type of problem to solve
            customer_emotion: Customer emotional state
            
        Returns:
            List of suitable workflows ordered by appropriateness
        """
        
        # Ensure workflows are loaded when lazy loading is enabled
        if not self._initialized:
            self._initialize_all_workflows()

        # Filter workflows by category
        category_workflows = [
            workflow for workflow in self.workflows.values()
            if workflow.problem_category == problem_category
        ]
        
        if not category_workflows:
            # Return generic workflow if no specific category workflows
            return [self._create_generic_workflow(problem_category)]
        
        # Sort workflows by appropriateness for customer emotion
        sorted_workflows = await self._sort_workflows_by_emotion(category_workflows, customer_emotion)
        
        logger.info(f"Found {len(sorted_workflows)} workflows for {problem_category.value} with {customer_emotion.value} emotion")
        
        return sorted_workflows
    
    async def get_workflow_by_name(self, workflow_name: str) -> Optional[TroubleshootingWorkflow]:
        """Get specific workflow by name"""
        if not self._initialized:
            self._initialize_all_workflows()
        return self.workflows.get(workflow_name)
    
    async def create_adaptive_workflow(
        self,
        base_workflow: TroubleshootingWorkflow,
        customer_technical_level: int,
        customer_emotion: EmotionalState,
        complexity_adjustment: int = 0
    ) -> TroubleshootingWorkflow:
        """
        Create adaptive workflow based on customer characteristics
        
        Args:
            base_workflow: Base workflow to adapt
            customer_technical_level: Customer technical skill (1-5)
            customer_emotion: Customer emotional state
            complexity_adjustment: Additional complexity adjustment (-2 to +2)
            
        Returns:
            Adapted workflow for specific customer
        """
        
        # Create copy of base workflow
        adapted_workflow = TroubleshootingWorkflow(
            name=f"{base_workflow.name} (Adapted)",
            description=base_workflow.description,
            problem_category=base_workflow.problem_category,
            applicable_symptoms=base_workflow.applicable_symptoms.copy(),
            phases=base_workflow.phases.copy(),
            diagnostic_steps=[],  # Will be populated with adapted steps
            verification_checkpoints=base_workflow.verification_checkpoints.copy(),
            escalation_criteria=base_workflow.escalation_criteria,
            estimated_time_minutes=base_workflow.estimated_time_minutes,
            success_rate=base_workflow.success_rate,
            difficulty_level=base_workflow.difficulty_level,
            required_tools=base_workflow.required_tools.copy(),
            required_permissions=base_workflow.required_permissions.copy()
        )
        
        # Adapt diagnostic steps
        for step in base_workflow.diagnostic_steps:
            adapted_step = await self._adapt_diagnostic_step(
                step, customer_technical_level, customer_emotion, complexity_adjustment
            )
            if adapted_step:  # Skip steps that are inappropriate for customer
                adapted_workflow.diagnostic_steps.append(adapted_step)
        
        # Adjust workflow metadata
        adapted_workflow.difficulty_level = max(1, min(5, 
            base_workflow.difficulty_level + complexity_adjustment))
        
        # Adjust estimated time based on customer technical level
        time_multiplier = self._get_time_multiplier(customer_technical_level, customer_emotion)
        adapted_workflow.estimated_time_minutes = int(
            base_workflow.estimated_time_minutes * time_multiplier)
        
        logger.info(f"Created adaptive workflow with {len(adapted_workflow.diagnostic_steps)} steps for level {customer_technical_level} customer")
        
        return adapted_workflow
    
    # Workflow initialization methods
    
    def _initialize_email_connectivity_workflows(self):
        """Initialize email connectivity troubleshooting workflows"""
        
        # Basic Email Connectivity Workflow (Level 1-2)
        basic_connectivity = TroubleshootingWorkflow(
            name="Basic Email Connectivity Resolution",
            description="Resolve basic email connection issues with simple diagnostic steps",
            problem_category=ProblemCategory.TECHNICAL_ISSUE,
            applicable_symptoms=[
                "emails not syncing", "connection errors", "cannot send emails",
                "authentication failed", "server timeout"
            ],
            phases=[
                TroubleshootingPhase.INITIAL_ASSESSMENT,
                TroubleshootingPhase.BASIC_DIAGNOSTICS,
                TroubleshootingPhase.RESOLUTION_VERIFICATION
            ],
            diagnostic_steps=self._create_basic_connectivity_steps(),
            verification_checkpoints=self._create_basic_verification_checkpoints(),
            escalation_criteria=EscalationCriteria(
                max_diagnostic_steps=6,
                max_time_minutes=20,
                max_failed_attempts=2,
                complexity_threshold=0.6
            ),
            estimated_time_minutes=15,
            success_rate=0.85,
            difficulty_level=2,
            required_tools=["account_settings", "connection_test"],
            required_permissions=["user_account_access"]
        )
        
        # Advanced Email Connectivity Workflow (Level 3-4)
        advanced_connectivity = TroubleshootingWorkflow(
            name="Advanced Email Connectivity Diagnosis",
            description="Comprehensive email connectivity troubleshooting with technical diagnostics",
            problem_category=ProblemCategory.TECHNICAL_ISSUE,
            applicable_symptoms=[
                "intermittent connection issues", "ssl/tls errors", "port configuration",
                "oauth authentication", "corporate firewall issues"
            ],
            phases=[
                TroubleshootingPhase.INITIAL_ASSESSMENT,
                TroubleshootingPhase.BASIC_DIAGNOSTICS,
                TroubleshootingPhase.INTERMEDIATE_DIAGNOSTICS,
                TroubleshootingPhase.ADVANCED_DIAGNOSTICS,
                TroubleshootingPhase.RESOLUTION_VERIFICATION
            ],
            diagnostic_steps=self._create_advanced_connectivity_steps(),
            verification_checkpoints=self._create_advanced_verification_checkpoints(),
            escalation_criteria=EscalationCriteria(
                max_diagnostic_steps=12,
                max_time_minutes=45,
                max_failed_attempts=3,
                complexity_threshold=0.8
            ),
            estimated_time_minutes=35,
            success_rate=0.75,
            difficulty_level=4,
            required_tools=["network_diagnostics", "ssl_analyzer", "port_scanner"],
            required_permissions=["network_access", "security_settings"]
        )
        
        self.workflows["basic_email_connectivity"] = basic_connectivity
        self.workflows["advanced_email_connectivity"] = advanced_connectivity
    
    def _initialize_account_setup_workflows(self):
        """Initialize account setup troubleshooting workflows"""
        
        account_setup = TroubleshootingWorkflow(
            name="Email Account Setup Assistant",
            description="Guide customer through email account setup with validation",
            problem_category=ProblemCategory.ACCOUNT_SETUP,
            applicable_symptoms=[
                "new account setup", "account configuration", "server settings",
                "email provider setup", "first time setup"
            ],
            phases=[
                TroubleshootingPhase.INITIAL_ASSESSMENT,
                TroubleshootingPhase.BASIC_DIAGNOSTICS,
                TroubleshootingPhase.RESOLUTION_VERIFICATION
            ],
            diagnostic_steps=self._create_account_setup_steps(),
            verification_checkpoints=self._create_setup_verification_checkpoints(),
            escalation_criteria=EscalationCriteria(
                max_diagnostic_steps=8,
                max_time_minutes=25,
                max_failed_attempts=2,
                complexity_threshold=0.5
            ),
            estimated_time_minutes=20,
            success_rate=0.90,
            difficulty_level=2,
            required_tools=["account_wizard", "server_database"],
            required_permissions=["account_creation"]
        )
        
        self.workflows["email_account_setup"] = account_setup
    
    def _initialize_sync_issue_workflows(self):
        """Initialize email synchronization troubleshooting workflows"""
        
        sync_issues = TroubleshootingWorkflow(
            name="Email Synchronization Resolution",
            description="Resolve email sync issues and folder synchronization problems",
            problem_category=ProblemCategory.TECHNICAL_ISSUE,
            applicable_symptoms=[
                "emails not updating", "missing emails", "duplicate emails",
                "folder sync issues", "delayed synchronization"
            ],
            phases=[
                TroubleshootingPhase.INITIAL_ASSESSMENT,
                TroubleshootingPhase.BASIC_DIAGNOSTICS,
                TroubleshootingPhase.INTERMEDIATE_DIAGNOSTICS,
                TroubleshootingPhase.RESOLUTION_VERIFICATION
            ],
            diagnostic_steps=self._create_sync_resolution_steps(),
            verification_checkpoints=self._create_sync_verification_checkpoints(),
            escalation_criteria=EscalationCriteria(
                max_diagnostic_steps=10,
                max_time_minutes=30,
                max_failed_attempts=3,
                complexity_threshold=0.7
            ),
            estimated_time_minutes=25,
            success_rate=0.80,
            difficulty_level=3,
            required_tools=["sync_manager", "folder_analyzer"],
            required_permissions=["email_access", "folder_management"]
        )
        
        self.workflows["email_sync_issues"] = sync_issues
    
    def _initialize_performance_workflows(self):
        """Initialize performance optimization workflows"""
        
        performance = TroubleshootingWorkflow(
            name="Mailbird Performance Optimization",
            description="Diagnose and resolve performance issues and slowdowns",
            problem_category=ProblemCategory.PERFORMANCE_OPTIMIZATION,
            applicable_symptoms=[
                "slow loading", "high memory usage", "application freezing",
                "slow email retrieval", "interface lag"
            ],
            phases=[
                TroubleshootingPhase.INITIAL_ASSESSMENT,
                TroubleshootingPhase.BASIC_DIAGNOSTICS,
                TroubleshootingPhase.INTERMEDIATE_DIAGNOSTICS,
                TroubleshootingPhase.RESOLUTION_VERIFICATION
            ],
            diagnostic_steps=self._create_performance_optimization_steps(),
            verification_checkpoints=self._create_performance_verification_checkpoints(),
            escalation_criteria=EscalationCriteria(
                max_diagnostic_steps=8,
                max_time_minutes=35,
                max_failed_attempts=2,
                complexity_threshold=0.7
            ),
            estimated_time_minutes=30,
            success_rate=0.75,
            difficulty_level=3,
            required_tools=["performance_monitor", "system_analyzer"],
            required_permissions=["system_access", "performance_data"]
        )
        
        self.workflows["performance_optimization"] = performance
    
    def _initialize_feature_education_workflows(self):
        """Initialize feature education workflows"""
        
        feature_education = TroubleshootingWorkflow(
            name="Mailbird Feature Education",
            description="Guide customer through feature usage and best practices",
            problem_category=ProblemCategory.FEATURE_EDUCATION,
            applicable_symptoms=[
                "how to use feature", "feature questions", "best practices",
                "feature not working as expected", "learning new features"
            ],
            phases=[
                TroubleshootingPhase.INITIAL_ASSESSMENT,
                TroubleshootingPhase.BASIC_DIAGNOSTICS,
                TroubleshootingPhase.RESOLUTION_VERIFICATION
            ],
            diagnostic_steps=self._create_feature_education_steps(),
            verification_checkpoints=self._create_education_verification_checkpoints(),
            escalation_criteria=EscalationCriteria(
                max_diagnostic_steps=6,
                max_time_minutes=20,
                max_failed_attempts=1,
                complexity_threshold=0.4
            ),
            estimated_time_minutes=15,
            success_rate=0.95,
            difficulty_level=1,
            required_tools=["feature_documentation", "tutorial_system"],
            required_permissions=["feature_access"]
        )
        
        self.workflows["feature_education"] = feature_education
    
    # Diagnostic step creation methods
    
    def _create_basic_connectivity_steps(self) -> List[DiagnosticStep]:
        """Create basic connectivity diagnostic steps"""
        return [
            DiagnosticStep(
                step_number=1,
                step_id="verify_account_credentials",
                step_type=DiagnosticStepType.INFORMATION_GATHERING,
                title="Verify Account Credentials",
                description="Confirm email address and password are correct",
                instructions="Please verify your email address and password are entered correctly in account settings",
                expected_outcome="Account credentials confirmed as accurate",
                time_estimate_minutes=3,
                difficulty_level=1,
                success_criteria=["credentials verified", "password accepted"],
                failure_indicators=["authentication failed", "invalid credentials"],
                troubleshooting_tips=[
                    "Check for typos in email address",
                    "Ensure caps lock is not on for password",
                    "Try copying and pasting credentials"
                ]
            ),
            DiagnosticStep(
                step_number=2,
                step_id="test_basic_connection",
                step_type=DiagnosticStepType.QUICK_TEST,
                title="Test Basic Connection",
                description="Perform basic connection test to email server",
                instructions="Click 'Test Connection' in account settings to verify server connectivity",
                expected_outcome="Connection test passes successfully",
                time_estimate_minutes=2,
                difficulty_level=1,
                success_criteria=["connection successful", "server responsive"],
                failure_indicators=["connection failed", "timeout error"],
                troubleshooting_tips=[
                    "Ensure internet connection is stable",
                    "Try testing again after a few seconds"
                ]
            ),
            DiagnosticStep(
                step_number=3,
                step_id="verify_server_settings",
                step_type=DiagnosticStepType.CONFIGURATION_CHECK,
                title="Verify Server Settings",
                description="Check incoming and outgoing server settings",
                instructions="Verify IMAP/POP and SMTP server settings match your email provider's requirements",
                expected_outcome="Server settings are correctly configured",
                time_estimate_minutes=5,
                difficulty_level=2,
                success_criteria=["server settings correct", "ports configured"],
                failure_indicators=["incorrect server", "wrong port numbers"],
                troubleshooting_tips=[
                    "Use automatic setup if available",
                    "Check email provider's help documentation",
                    "Ensure SSL/TLS settings are correct"
                ]
            ),
            DiagnosticStep(
                step_number=4,
                step_id="restart_application",
                step_type=DiagnosticStepType.SYSTEM_VERIFICATION,
                title="Restart Application",
                description="Restart Mailbird to refresh connection",
                instructions="Close Mailbird completely and restart the application",
                expected_outcome="Application restarts and attempts reconnection",
                time_estimate_minutes=2,
                difficulty_level=1,
                success_criteria=["application restarted", "connection attempted"],
                failure_indicators=["application won't start", "immediate error"],
                troubleshooting_tips=[
                    "Ensure application is completely closed",
                    "Wait 10 seconds before restarting"
                ]
            ),
            DiagnosticStep(
                step_number=5,
                step_id="test_email_send_receive",
                step_type=DiagnosticStepType.CONNECTIVITY_TEST,
                title="Test Email Send/Receive",
                description="Send a test email to verify full functionality",
                instructions="Send a test email to yourself and check if it's received",
                expected_outcome="Test email successfully sent and received",
                time_estimate_minutes=3,
                difficulty_level=1,
                success_criteria=["email sent", "email received"],
                failure_indicators=["send failed", "email not received"],
                troubleshooting_tips=[
                    "Check spam/junk folders",
                    "Try sending to a different email address",
                    "Wait a few minutes for delivery"
                ]
            )
        ]
    
    def _create_advanced_connectivity_steps(self) -> List[DiagnosticStep]:
        """Create advanced connectivity diagnostic steps"""
        basic_steps = self._create_basic_connectivity_steps()
        
        advanced_steps = [
            DiagnosticStep(
                step_number=6,
                step_id="network_diagnostics",
                step_type=DiagnosticStepType.NETWORK_TEST,
                title="Network Diagnostics",
                description="Perform comprehensive network connectivity analysis",
                instructions="Run network diagnostic tools to check for connectivity issues",
                expected_outcome="Network connectivity analysis completed",
                time_estimate_minutes=5,
                difficulty_level=3,
                success_criteria=["network analysis complete", "connectivity confirmed"],
                failure_indicators=["network issues detected", "connectivity blocked"],
                troubleshooting_tips=[
                    "Check firewall settings",
                    "Verify proxy configuration",
                    "Test with different network if possible"
                ]
            ),
            DiagnosticStep(
                step_number=7,
                step_id="ssl_tls_validation",
                step_type=DiagnosticStepType.CONFIGURATION_CHECK,
                title="SSL/TLS Certificate Validation",
                description="Verify SSL/TLS certificates and encryption settings",
                instructions="Check SSL/TLS certificate validity and encryption protocols",
                expected_outcome="SSL/TLS certificates validated successfully",
                time_estimate_minutes=4,
                difficulty_level=4,
                success_criteria=["certificates valid", "encryption working"],
                failure_indicators=["certificate error", "encryption failed"],
                troubleshooting_tips=[
                    "Update application to latest version",
                    "Check system date and time",
                    "Try different encryption settings"
                ]
            ),
            DiagnosticStep(
                step_number=8,
                step_id="oauth_authentication_check",
                step_type=DiagnosticStepType.SYSTEM_VERIFICATION,
                title="OAuth Authentication Check",
                description="Verify OAuth 2.0 authentication flow",
                instructions="Re-authenticate using OAuth if supported by email provider",
                expected_outcome="OAuth authentication completed successfully",
                time_estimate_minutes=6,
                difficulty_level=3,
                success_criteria=["oauth successful", "token refreshed"],
                failure_indicators=["oauth failed", "token expired"],
                troubleshooting_tips=[
                    "Clear browser cache before OAuth",
                    "Ensure pop-ups are allowed",
                    "Check two-factor authentication settings"
                ]
            )
        ]
        
        return basic_steps + advanced_steps
    
    def _create_account_setup_steps(self) -> List[DiagnosticStep]:
        """Create account setup diagnostic steps"""
        return [
            DiagnosticStep(
                step_number=1,
                step_id="collect_account_info",
                step_type=DiagnosticStepType.INFORMATION_GATHERING,
                title="Collect Account Information",
                description="Gather email provider and account details",
                instructions="Please provide your email address and email provider (Gmail, Outlook, etc.)",
                expected_outcome="Account information collected",
                time_estimate_minutes=2,
                difficulty_level=1,
                success_criteria=["email provided", "provider identified"],
                failure_indicators=["incomplete information", "unknown provider"],
                troubleshooting_tips=[
                    "Check email address format",
                    "Identify email domain (gmail.com, outlook.com, etc.)"
                ]
            ),
            DiagnosticStep(
                step_number=2,
                step_id="auto_configure_account",
                step_type=DiagnosticStepType.CONFIGURATION_CHECK,
                title="Auto-Configure Account",
                description="Attempt automatic account configuration",
                instructions="Use Mailbird's automatic setup to configure your account",
                expected_outcome="Account automatically configured",
                time_estimate_minutes=3,
                difficulty_level=1,
                success_criteria=["auto-setup successful", "settings detected"],
                failure_indicators=["auto-setup failed", "manual config needed"],
                troubleshooting_tips=[
                    "Ensure internet connection is stable",
                    "Try manual setup if auto-setup fails"
                ]
            ),
            DiagnosticStep(
                step_number=3,
                step_id="validate_account_credentials",
                step_type=DiagnosticStepType.ACCOUNT_VALIDATION,
                title="Validate Account Credentials",
                description="Test account credentials and permissions",
                instructions="Enter your email password and test the connection",
                expected_outcome="Account credentials validated",
                time_estimate_minutes=3,
                difficulty_level=2,
                success_criteria=["password accepted", "permissions granted"],
                failure_indicators=["invalid password", "access denied"],
                troubleshooting_tips=[
                    "Use app-specific password if 2FA is enabled",
                    "Check email provider's security settings"
                ]
            ),
            DiagnosticStep(
                step_number=4,
                step_id="initial_sync_test",
                step_type=DiagnosticStepType.CONNECTIVITY_TEST,
                title="Initial Sync Test",
                description="Perform initial email synchronization",
                instructions="Allow Mailbird to perform initial email sync",
                expected_outcome="Initial sync completed successfully",
                time_estimate_minutes=5,
                difficulty_level=2,
                success_criteria=["sync started", "emails downloading"],
                failure_indicators=["sync failed", "no emails found"],
                troubleshooting_tips=[
                    "Initial sync may take several minutes",
                    "Check folder settings if emails seem missing"
                ]
            )
        ]
    
    def _create_sync_resolution_steps(self) -> List[DiagnosticStep]:
        """Create sync resolution diagnostic steps"""
        return [
            DiagnosticStep(
                step_number=1,
                step_id="force_manual_sync",
                step_type=DiagnosticStepType.QUICK_TEST,
                title="Force Manual Sync",
                description="Trigger manual synchronization to refresh emails",
                instructions="Right-click on account and select 'Sync Now' to force synchronization",
                expected_outcome="Manual sync initiated and completed",
                time_estimate_minutes=3,
                difficulty_level=1,
                success_criteria=["sync triggered", "sync completed"],
                failure_indicators=["sync failed", "sync timeout"],
                troubleshooting_tips=[
                    "Wait for sync to complete before testing",
                    "Check sync status indicators"
                ]
            ),
            DiagnosticStep(
                step_number=2,
                step_id="review_sync_settings",
                step_type=DiagnosticStepType.CONFIGURATION_CHECK,
                title="Review Sync Settings",
                description="Check synchronization frequency and folder settings",
                instructions="Review sync frequency and ensure all desired folders are set to sync",
                expected_outcome="Sync settings optimized",
                time_estimate_minutes=4,
                difficulty_level=2,
                success_criteria=["settings reviewed", "folders configured"],
                failure_indicators=["settings incorrect", "folders excluded"],
                troubleshooting_tips=[
                    "Enable sync for important folders",
                    "Adjust sync frequency based on needs"
                ]
            ),
            DiagnosticStep(
                step_number=3,
                step_id="clear_sync_cache",
                step_type=DiagnosticStepType.SYSTEM_VERIFICATION,
                title="Clear Sync Cache",
                description="Clear local sync cache to resolve sync conflicts",
                instructions="Clear the local email cache and restart synchronization",
                expected_outcome="Cache cleared and sync restarted",
                time_estimate_minutes=5,
                difficulty_level=3,
                success_criteria=["cache cleared", "sync restarted"],
                failure_indicators=["cache not cleared", "sync issues persist"],
                troubleshooting_tips=[
                    "Backup important local data first",
                    "Allow time for complete re-sync"
                ]
            )
        ]
    
    def _create_performance_optimization_steps(self) -> List[DiagnosticStep]:
        """Create performance optimization diagnostic steps"""
        return [
            DiagnosticStep(
                step_number=1,
                step_id="system_resource_check",
                step_type=DiagnosticStepType.PERFORMANCE_ANALYSIS,
                title="System Resource Check",
                description="Analyze system resource usage and availability",
                instructions="Check available memory, CPU usage, and disk space",
                expected_outcome="System resources analyzed",
                time_estimate_minutes=3,
                difficulty_level=2,
                success_criteria=["resources checked", "bottlenecks identified"],
                failure_indicators=["resource constraints", "system overloaded"],
                troubleshooting_tips=[
                    "Close unnecessary applications",
                    "Check available memory and disk space"
                ]
            ),
            DiagnosticStep(
                step_number=2,
                step_id="optimize_sync_settings",
                step_type=DiagnosticStepType.CONFIGURATION_CHECK,
                title="Optimize Sync Settings",
                description="Adjust synchronization settings for better performance",
                instructions="Reduce sync frequency for large accounts and disable unnecessary integrations",
                expected_outcome="Sync settings optimized for performance",
                time_estimate_minutes=4,
                difficulty_level=2,
                success_criteria=["settings optimized", "performance improved"],
                failure_indicators=["settings unchanged", "performance issues persist"],
                troubleshooting_tips=[
                    "Reduce sync frequency for large mailboxes",
                    "Disable unused app integrations"
                ]
            ),
            DiagnosticStep(
                step_number=3,
                step_id="application_update_check",
                step_type=DiagnosticStepType.SYSTEM_VERIFICATION,
                title="Application Update Check",
                description="Ensure Mailbird is updated to latest version",
                instructions="Check for and install any available Mailbird updates",
                expected_outcome="Application updated to latest version",
                time_estimate_minutes=5,
                difficulty_level=1,
                success_criteria=["update checked", "latest version installed"],
                failure_indicators=["update failed", "old version running"],
                troubleshooting_tips=[
                    "Restart application after update",
                    "Check system requirements for new version"
                ]
            )
        ]
    
    def _create_feature_education_steps(self) -> List[DiagnosticStep]:
        """Create feature education diagnostic steps"""
        return [
            DiagnosticStep(
                step_number=1,
                step_id="identify_feature_interest",
                step_type=DiagnosticStepType.INFORMATION_GATHERING,
                title="Identify Feature Interest",
                description="Understand which feature the customer wants to learn",
                instructions="Please specify which Mailbird feature you'd like to learn about",
                expected_outcome="Specific feature identified",
                time_estimate_minutes=2,
                difficulty_level=1,
                success_criteria=["feature specified", "learning goal clear"],
                failure_indicators=["unclear request", "multiple features"],
                troubleshooting_tips=[
                    "Focus on one feature at a time",
                    "Clarify the intended use case"
                ]
            ),
            DiagnosticStep(
                step_number=2,
                step_id="feature_demonstration",
                step_type=DiagnosticStepType.QUICK_TEST,
                title="Feature Demonstration",
                description="Demonstrate basic feature usage",
                instructions="Follow along as we demonstrate the key aspects of this feature",
                expected_outcome="Feature usage demonstrated",
                time_estimate_minutes=5,
                difficulty_level=1,
                success_criteria=["demonstration completed", "steps understood"],
                failure_indicators=["feature not found", "steps unclear"],
                troubleshooting_tips=[
                    "Take your time with each step",
                    "Ask questions if anything is unclear"
                ]
            ),
            DiagnosticStep(
                step_number=3,
                step_id="practice_feature_usage",
                step_type=DiagnosticStepType.SYSTEM_VERIFICATION,
                title="Practice Feature Usage",
                description="Practice using the feature independently",
                instructions="Try using the feature on your own to reinforce learning",
                expected_outcome="Feature used successfully independently",
                time_estimate_minutes=4,
                difficulty_level=2,
                success_criteria=["feature used independently", "confident usage"],
                failure_indicators=["unable to use feature", "confusion persists"],
                troubleshooting_tips=[
                    "Practice with simple examples first",
                    "Reference help documentation as needed"
                ]
            )
        ]
    
    # Verification checkpoint creation methods
    
    def _create_basic_verification_checkpoints(self) -> List[VerificationCheckpoint]:
        """Create basic verification checkpoints"""
        return [
            VerificationCheckpoint(
                name="Connection Established",
                description="Verify basic email connection is working",
                verification_questions=[
                    "Is the email account connecting successfully?",
                    "Are emails being synchronized?"
                ],
                success_indicators=["connection successful", "emails syncing"],
                failure_indicators=["connection failed", "no sync activity"],
                verification_method="connection_test",
                required_evidence=["connection status", "sync activity"]
            )
        ]
    
    def _create_advanced_verification_checkpoints(self) -> List[VerificationCheckpoint]:
        """Create advanced verification checkpoints"""
        return [
            VerificationCheckpoint(
                name="Advanced Connectivity Verified",
                description="Verify advanced connectivity features are working",
                verification_questions=[
                    "Are all security protocols functioning correctly?",
                    "Is the connection stable under various conditions?"
                ],
                success_indicators=["security protocols active", "stable connection"],
                failure_indicators=["security issues", "intermittent connectivity"],
                verification_method="comprehensive_connectivity_test",
                required_evidence=["security status", "stability metrics"]
            )
        ]
    
    def _create_setup_verification_checkpoints(self) -> List[VerificationCheckpoint]:
        """Create account setup verification checkpoints"""
        return [
            VerificationCheckpoint(
                name="Account Setup Complete",
                description="Verify account is properly configured and functional",
                verification_questions=[
                    "Is the account properly configured?",
                    "Can emails be sent and received successfully?"
                ],
                success_indicators=["account configured", "send/receive working"],
                failure_indicators=["configuration incomplete", "send/receive failed"],
                verification_method="account_functionality_test",
                required_evidence=["configuration status", "email test results"]
            )
        ]
    
    def _create_sync_verification_checkpoints(self) -> List[VerificationCheckpoint]:
        """Create sync verification checkpoints"""
        return [
            VerificationCheckpoint(
                name="Sync Resolution Verified",
                description="Verify email synchronization is working properly",
                verification_questions=[
                    "Are emails synchronizing correctly?",
                    "Are all folders updating as expected?"
                ],
                success_indicators=["sync working", "folders updated"],
                failure_indicators=["sync issues", "folders not updating"],
                verification_method="sync_functionality_test",
                required_evidence=["sync status", "folder update activity"]
            )
        ]
    
    def _create_performance_verification_checkpoints(self) -> List[VerificationCheckpoint]:
        """Create performance verification checkpoints"""
        return [
            VerificationCheckpoint(
                name="Performance Improved",
                description="Verify performance optimizations are effective",
                verification_questions=[
                    "Is the application running faster?",
                    "Are resource usage levels acceptable?"
                ],
                success_indicators=["improved speed", "optimized resource usage"],
                failure_indicators=["still slow", "high resource usage"],
                verification_method="performance_test",
                required_evidence=["performance metrics", "resource usage data"]
            )
        ]
    
    def _create_education_verification_checkpoints(self) -> List[VerificationCheckpoint]:
        """Create feature education verification checkpoints"""
        return [
            VerificationCheckpoint(
                name="Feature Learning Complete",
                description="Verify customer has learned to use the feature effectively",
                verification_questions=[
                    "Can the customer use the feature independently?",
                    "Does the customer understand the feature's benefits?"
                ],
                success_indicators=["independent usage", "understanding demonstrated"],
                failure_indicators=["unable to use independently", "confusion persists"],
                verification_method="feature_competency_test",
                required_evidence=["usage demonstration", "comprehension confirmation"]
            )
        ]
    
    # Helper methods
    
    async def _sort_workflows_by_emotion(
        self,
        workflows: List[TroubleshootingWorkflow],
        customer_emotion: EmotionalState
    ) -> List[TroubleshootingWorkflow]:
        """Sort workflows by appropriateness for customer emotional state"""
        
        def emotion_score(workflow: TroubleshootingWorkflow) -> float:
            score = 0.0
            
            # Prefer shorter workflows for frustrated/urgent customers
            if customer_emotion in [EmotionalState.FRUSTRATED, EmotionalState.URGENT]:
                time_factor = max(0.1, 1.0 - (workflow.estimated_time_minutes / 60))
                score += time_factor * 0.4
                
                # Prefer simpler workflows
                simplicity_factor = max(0.1, 1.0 - (workflow.difficulty_level / 5))
                score += simplicity_factor * 0.3
            
            # Prefer simpler workflows for confused customers
            elif customer_emotion == EmotionalState.CONFUSED:
                simplicity_factor = max(0.1, 1.0 - (workflow.difficulty_level / 5))
                score += simplicity_factor * 0.5
            
            # Allow complex workflows for professional customers
            elif customer_emotion == EmotionalState.PROFESSIONAL:
                complexity_bonus = workflow.difficulty_level / 5
                score += complexity_bonus * 0.2
            
            # Base score from success rate
            score += workflow.success_rate * 0.3
            
            return score
        
        return sorted(workflows, key=emotion_score, reverse=True)
    
    async def _adapt_diagnostic_step(
        self,
        step: DiagnosticStep,
        customer_technical_level: int,
        customer_emotion: EmotionalState,
        complexity_adjustment: int
    ) -> Optional[DiagnosticStep]:
        """Adapt diagnostic step for customer characteristics"""
        
        # Skip steps that are too advanced for customer
        adjusted_difficulty = step.difficulty_level + complexity_adjustment
        if adjusted_difficulty > customer_technical_level + 2:
            return None  # Skip this step
        
        # Create adapted copy
        adapted_step = DiagnosticStep(
            step_id=step.step_id,
            step_number=step.step_number,
            step_type=step.step_type,
            title=step.title,
            description=step.description,
            instructions=step.instructions,
            expected_outcome=step.expected_outcome,
            time_estimate_minutes=step.time_estimate_minutes,
            difficulty_level=max(1, adjusted_difficulty),
            prerequisites=step.prerequisites.copy(),
            success_criteria=step.success_criteria.copy(),
            failure_indicators=step.failure_indicators.copy(),
            next_steps_on_success=step.next_steps_on_success.copy(),
            next_steps_on_failure=step.next_steps_on_failure.copy(),
            verification_method=step.verification_method,
            troubleshooting_tips=step.troubleshooting_tips.copy(),
            common_issues=step.common_issues.copy()
        )
        
        # Adapt instructions based on customer technical level
        if customer_technical_level <= 2:
            # Simplify instructions for beginners
            adapted_step.instructions = f"📋 Simple steps: {adapted_step.instructions}"
            adapted_step.troubleshooting_tips.insert(0, "Take your time with each step")
            
        elif customer_technical_level >= 4:
            # Add technical details for advanced users
            adapted_step.troubleshooting_tips.append("Advanced users can check system logs for additional details")
        
        # Adapt based on emotional state
        if customer_emotion == EmotionalState.FRUSTRATED:
            adapted_step.instructions = f"⚡ Quick approach: {adapted_step.instructions}"
            adapted_step.time_estimate_minutes = max(1, adapted_step.time_estimate_minutes - 1)
            
        elif customer_emotion == EmotionalState.ANXIOUS:
            adapted_step.instructions = f"🔍 Careful method: {adapted_step.instructions}"
            adapted_step.troubleshooting_tips.insert(0, "This is a safe step that won't cause any issues")
            
        elif customer_emotion == EmotionalState.CONFUSED:
            adapted_step.instructions = f"📖 Clear guidance: {adapted_step.instructions}"
            adapted_step.troubleshooting_tips.insert(0, "Follow each step carefully and don't worry if it takes time")
        
        return adapted_step
    
    def _get_time_multiplier(
        self,
        customer_technical_level: int,
        customer_emotion: EmotionalState
    ) -> float:
        """Get time multiplier for workflow adaptation"""
        
        multiplier = 1.0
        
        # Adjust for technical level
        if customer_technical_level <= 2:
            multiplier *= 1.5  # Beginners need more time
        elif customer_technical_level >= 4:
            multiplier *= 0.8  # Advanced users are faster
        
        # Adjust for emotional state
        if customer_emotion in [EmotionalState.FRUSTRATED, EmotionalState.URGENT]:
            multiplier *= 0.9  # Try to be faster for urgent customers
        elif customer_emotion == EmotionalState.CONFUSED:
            multiplier *= 1.3  # Confused customers need more time
        
        return multiplier
    
    def _create_generic_workflow(self, problem_category: ProblemCategory) -> TroubleshootingWorkflow:
        """Create generic workflow for unknown problem categories"""
        
        return TroubleshootingWorkflow(
            name=f"Generic {problem_category.value.replace('_', ' ').title()} Resolution",
            description=f"General troubleshooting approach for {problem_category.value.replace('_', ' ')} issues",
            problem_category=problem_category,
            applicable_symptoms=["general issues", "unspecified problems"],
            phases=[
                TroubleshootingPhase.INITIAL_ASSESSMENT,
                TroubleshootingPhase.BASIC_DIAGNOSTICS,
                TroubleshootingPhase.RESOLUTION_VERIFICATION
            ],
            diagnostic_steps=[
                DiagnosticStep(
                    step_number=1,
                    step_type=DiagnosticStepType.INFORMATION_GATHERING,
                    title="Gather Problem Details",
                    description="Collect detailed information about the issue",
                    instructions="Please provide specific details about what you're experiencing",
                    expected_outcome="Problem details collected",
                    time_estimate_minutes=5,
                    difficulty_level=1,
                    success_criteria=["details provided", "problem understood"],
                    failure_indicators=["insufficient details", "unclear problem"]
                ),
                DiagnosticStep(
                    step_number=2,
                    step_type=DiagnosticStepType.QUICK_TEST,
                    title="Basic Troubleshooting",
                    description="Apply basic troubleshooting steps",
                    instructions="Try restarting the application and testing basic functionality",
                    expected_outcome="Basic troubleshooting completed",
                    time_estimate_minutes=5,
                    difficulty_level=1,
                    success_criteria=["restart completed", "basic test performed"],
                    failure_indicators=["restart failed", "basic functions not working"]
                )
            ],
            verification_checkpoints=[
                VerificationCheckpoint(
                    name="Generic Issue Resolution",
                    description="Verify issue has been addressed",
                    verification_questions=["Is the issue resolved or improved?"],
                    success_indicators=["issue resolved", "improvement noted"],
                    failure_indicators=["issue persists", "no improvement"],
                    verification_method="general_verification",
                    required_evidence=["issue status", "functionality test"]
                )
            ],
            escalation_criteria=EscalationCriteria(
                max_diagnostic_steps=4,
                max_time_minutes=20,
                max_failed_attempts=2,
                complexity_threshold=0.5
            ),
            estimated_time_minutes=15,
            success_rate=0.60,
            difficulty_level=2,
            required_tools=["basic_diagnostics"],
            required_permissions=["user_access"]
        )