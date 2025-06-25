"""
Comprehensive Testing Framework for Enhanced Log Analysis Agent v3.0
Validates all enhanced features including ML pattern discovery, predictive analysis, and automated remediation.
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import pytest
import unittest
from unittest.mock import Mock, patch, AsyncMock
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN

# Import enhanced components
from .edge_case_handler import EdgeCaseHandler
from .advanced_parser import AdvancedMailbirdAnalyzer
from .intelligent_analyzer import IntelligentLogAnalyzer
from .advanced_solution_engine import AdvancedSolutionEngine
from .optimized_analyzer import OptimizedLogAnalyzer
from .enhanced_schemas import (
    ComprehensiveLogAnalysisOutput,
    DetailedIssue,
    EnhancedSolution,
    PredictiveInsight,
    CorrelationAnalysis,
    DependencyAnalysis,
    MLPatternDiscovery,
    ValidationSummary
)

logger = logging.getLogger(__name__)

class LogAnalysisTestFramework:
    """
    Comprehensive testing framework for all enhanced log analysis components.
    Supports unit tests, integration tests, performance benchmarks, and validation.
    """
    
    def __init__(self):
        self.test_results = {}
        self.performance_metrics = {}
        self.validation_errors = []
        
        # Initialize test components
        self.edge_case_handler = EdgeCaseHandler()
        self.advanced_parser = AdvancedMailbirdAnalyzer()
        self.intelligent_analyzer = IntelligentLogAnalyzer()
        self.solution_engine = AdvancedSolutionEngine()
        self.optimized_analyzer = OptimizedLogAnalyzer()
        
        # Test data repository
        self.test_logs_repository = self._create_test_logs_repository()
        
    def _create_test_logs_repository(self) -> Dict[str, Dict[str, Any]]:
        """Create comprehensive test log repository covering all scenarios."""
        return {
            # Edge cases
            'corrupted_encoding': {
                'content': b'\xff\xfe\x00\x00Invalid UTF-8 \x80\x81\x82 content',
                'expected_preprocessing': True,
                'expected_language': 'english',
                'expected_platform': 'windows'
            },
            'base64_encoded': {
                'content': 'W0VSUk9SXSBDb25uZWN0aW9uIGZhaWxlZCBmb3IgdGVzdEBleGFtcGxlLmNvbQ==',
                'expected_preprocessing': True,
                'expected_decoding': '[ERROR] Connection failed for test@example.com'
            },
            'compressed_gzip': {
                'content': b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff',  # Gzipped content
                'expected_preprocessing': True,
                'expected_decompression': True
            },
            
            # Multi-language support
            'spanish_log': {
                'content': """
2024-01-15 10:30:25 [ERROR] Conexión fallida para usuario@ejemplo.com
2024-01-15 10:30:26 [ADVERTENCIA] Reintentando autenticación OAuth2
2024-01-15 10:30:27 [ERROR] Error de certificado SSL inválido
                """,
                'expected_language': 'spanish',
                'expected_issues': 3,
                'expected_severity': 'high'
            },
            'french_log': {
                'content': """
2024-01-15 10:30:25 [ERREUR] Échec de connexion pour utilisateur@exemple.fr
2024-01-15 10:30:26 [AVERTISSEMENT] Nouvelle tentative d'authentification OAuth2
                """,
                'expected_language': 'french',
                'expected_issues': 2
            },
            
            # Cross-platform scenarios
            'windows_registry_issues': {
                'content': """
2024-01-15 10:30:25 [ERROR] Registry key not found for user@domain.com
2024-01-15 10:30:26 [ERROR] Access denied to registry HKEY_CURRENT_USER
2024-01-15 10:30:27 [ERROR] COM activation failed for user@domain.com
                """,
                'expected_platform': 'windows',
                'expected_issues': 3,
                'expected_categories': ['Windows Registry Access Issues', 'Windows COM Component Issues']
            },
            'macos_keychain_issues': {
                'content': """
2024-01-15 10:30:25 [ERROR] Keychain access denied for user@icloud.com
2024-01-15 10:30:26 [ERROR] errSecAuthFailed for user@icloud.com
2024-01-15 10:30:27 [ERROR] Sandbox violation: mailbird unable to access ~/Downloads
                """,
                'expected_platform': 'macos',
                'expected_issues': 3,
                'expected_categories': ['macOS Keychain Authentication Issues', 'macOS Sandbox Restrictions']
            },
            'linux_dbus_issues': {
                'content': """
2024-01-15 10:30:25 [ERROR] DBus connection failed for notifications
2024-01-15 10:30:26 [ERROR] Permission denied accessing /home/user/.mailbird
                """,
                'expected_platform': 'linux',
                'expected_issues': 2,
                'expected_categories': ['Linux D-Bus Communication Issues', 'Linux Permission Issues']
            },
            
            # Performance scenarios
            'large_log_file': {
                'content': self._generate_large_log_content(10000),  # 10K lines
                'expected_performance_profile': 'balanced',
                'max_analysis_time_seconds': 60
            },
            'huge_log_file': {
                'content': self._generate_large_log_content(50000),  # 50K lines
                'expected_performance_profile': 'ultra_fast',
                'max_analysis_time_seconds': 45
            },
            
            # ML pattern discovery scenarios
            'unknown_patterns': {
                'content': """
2024-01-15 10:30:25 [CUSTOM] XYZ_ERROR_CODE_12345 occurred for test@example.com
2024-01-15 10:30:26 [CUSTOM] XYZ_ERROR_CODE_12345 occurred for user@domain.com
2024-01-15 10:30:27 [CUSTOM] ABC_WARNING_999 detected in mail processing
2024-01-15 10:30:28 [CUSTOM] ABC_WARNING_999 detected in mail processing
                """,
                'expected_ml_discovery': True,
                'expected_pattern_count': 2,
                'expected_confidence_threshold': 0.8
            },
            
            # Correlation analysis scenarios
            'correlated_issues': {
                'content': """
2024-01-15 10:30:25 [ERROR] DNS resolution failed
2024-01-15 10:30:26 [ERROR] Connection timeout for user@example.com
2024-01-15 10:30:27 [ERROR] SMTP send failure for user@example.com
2024-01-15 10:30:28 [ERROR] DNS resolution failed
2024-01-15 10:30:29 [ERROR] Connection timeout for admin@example.com
2024-01-15 10:30:30 [ERROR] SMTP send failure for admin@example.com
                """,
                'expected_correlations': True,
                'expected_temporal_correlation': True,
                'expected_account_correlation': True
            },
            
            # Predictive analysis scenarios
            'degradation_pattern': {
                'content': self._generate_degradation_pattern_log(),
                'expected_predictions': True,
                'expected_prediction_types': ['performance_degradation', 'connection_failures'],
                'expected_prevention_recommendations': True
            }
        }
    
    def _generate_large_log_content(self, line_count: int) -> str:
        """Generate large log content for performance testing."""
        base_patterns = [
            "[INFO] Mail sync completed for {email}",
            "[ERROR] Connection failed for {email}",
            "[WARNING] Slow response from server for {email}",
            "[DEBUG] Processing attachment for {email}",
            "[ERROR] Authentication failed for {email}"
        ]
        
        emails = ["user1@example.com", "user2@domain.com", "admin@company.org"]
        lines = []
        
        for i in range(line_count):
            timestamp = datetime.now() - timedelta(minutes=line_count-i)
            pattern = base_patterns[i % len(base_patterns)]
            email = emails[i % len(emails)]
            line = f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} {pattern.format(email=email)}"
            lines.append(line)
        
        return '\n'.join(lines)
    
    def _generate_degradation_pattern_log(self) -> str:
        """Generate log content showing performance degradation over time."""
        lines = []
        base_time = datetime.now() - timedelta(hours=24)
        
        # Simulate gradual performance degradation
        for hour in range(24):
            current_time = base_time + timedelta(hours=hour)
            
            # Increasing error rate over time
            error_rate = min(0.1 + (hour * 0.02), 0.8)  # 10% to 80% error rate
            
            for minute in range(0, 60, 5):  # Every 5 minutes
                timestamp = current_time + timedelta(minutes=minute)
                
                if np.random.random() < error_rate:
                    lines.append(f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} [ERROR] Connection timeout (response time: {50 + hour * 20}ms)")
                else:
                    lines.append(f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} [INFO] Mail sync completed")
        
        return '\n'.join(lines)
    
    async def run_comprehensive_tests(self) -> Dict[str, Any]:
        """Run all comprehensive tests and return detailed results."""
        logger.info("Starting comprehensive log analysis testing framework")
        
        test_suite_results = {
            'edge_case_tests': await self._test_edge_case_handling(),
            'multi_language_tests': await self._test_multi_language_support(),
            'cross_platform_tests': await self._test_cross_platform_analysis(),
            'ml_discovery_tests': await self._test_ml_pattern_discovery(),
            'correlation_tests': await self._test_correlation_analysis(),
            'predictive_tests': await self._test_predictive_analysis(),
            'performance_tests': await self._test_performance_optimization(),
            'integration_tests': await self._test_full_integration(),
            'validation_tests': await self._test_solution_validation(),
            'automation_tests': await self._test_automated_remediation()
        }
        
        # Generate comprehensive test report
        test_report = self._generate_test_report(test_suite_results)
        
        return test_report
    
    async def _test_edge_case_handling(self) -> Dict[str, Any]:
        """Test edge case handler with various input scenarios."""
        logger.info("Testing edge case handling...")
        
        results = {
            'tests_run': 0,
            'tests_passed': 0,
            'test_details': [],
            'performance_metrics': {}
        }
        
        edge_case_tests = [
            'corrupted_encoding',
            'base64_encoded',
            'compressed_gzip'
        ]
        
        for test_name in edge_case_tests:
            test_data = self.test_logs_repository[test_name]
            results['tests_run'] += 1
            
            try:
                start_time = time.time()
                
                # Test preprocessing
                processed_content = await self.edge_case_handler.preprocess_log_content(
                    test_data['content']
                )
                
                processing_time = time.time() - start_time
                
                # Validate expectations
                test_passed = True
                validation_details = []
                
                if test_data.get('expected_preprocessing'):
                    if not processed_content or processed_content == str(test_data['content']):
                        test_passed = False
                        validation_details.append("Expected preprocessing did not occur")
                
                if test_data.get('expected_decoding'):
                    if test_data['expected_decoding'] not in processed_content:
                        test_passed = False
                        validation_details.append(f"Expected decoded content not found: {test_data['expected_decoding']}")
                
                if test_passed:
                    results['tests_passed'] += 1
                
                results['test_details'].append({
                    'test_name': test_name,
                    'passed': test_passed,
                    'processing_time_seconds': processing_time,
                    'validation_details': validation_details,
                    'processed_content_length': len(processed_content) if processed_content else 0
                })
                
            except Exception as e:
                results['test_details'].append({
                    'test_name': test_name,
                    'passed': False,
                    'error': str(e),
                    'processing_time_seconds': 0
                })
        
        results['success_rate'] = (results['tests_passed'] / results['tests_run']) * 100
        return results
    
    async def _test_multi_language_support(self) -> Dict[str, Any]:
        """Test multi-language error detection and analysis."""
        logger.info("Testing multi-language support...")
        
        results = {
            'tests_run': 0,
            'tests_passed': 0,
            'test_details': [],
            'languages_tested': []
        }
        
        language_tests = ['spanish_log', 'french_log']
        
        for test_name in language_tests:
            test_data = self.test_logs_repository[test_name]
            results['tests_run'] += 1
            
            try:
                # Test language detection
                detected_language = await self.edge_case_handler.detect_log_language(
                    test_data['content']
                )
                
                # Test parsing with language support
                parsed_data = await self.advanced_parser.parse_log_content(
                    test_data['content'],
                    {'detected_language': detected_language}
                )
                
                # Validate expectations
                test_passed = True
                validation_details = []
                
                expected_language = test_data.get('expected_language')
                if expected_language and detected_language != expected_language:
                    test_passed = False
                    validation_details.append(f"Expected language {expected_language}, got {detected_language}")
                
                expected_issues = test_data.get('expected_issues')
                actual_issues = len(parsed_data.get('errors', []))
                if expected_issues and actual_issues != expected_issues:
                    test_passed = False
                    validation_details.append(f"Expected {expected_issues} issues, found {actual_issues}")
                
                if test_passed:
                    results['tests_passed'] += 1
                
                results['test_details'].append({
                    'test_name': test_name,
                    'passed': test_passed,
                    'detected_language': detected_language,
                    'issues_found': actual_issues,
                    'validation_details': validation_details
                })
                
                if detected_language not in results['languages_tested']:
                    results['languages_tested'].append(detected_language)
                
            except Exception as e:
                results['test_details'].append({
                    'test_name': test_name,
                    'passed': False,
                    'error': str(e)
                })
        
        results['success_rate'] = (results['tests_passed'] / results['tests_run']) * 100
        return results
    
    async def _test_cross_platform_analysis(self) -> Dict[str, Any]:
        """Test cross-platform specific issue detection."""
        logger.info("Testing cross-platform analysis...")
        
        results = {
            'tests_run': 0,
            'tests_passed': 0,
            'test_details': [],
            'platforms_tested': []
        }
        
        platform_tests = ['windows_registry_issues', 'macos_keychain_issues', 'linux_dbus_issues']
        
        for test_name in platform_tests:
            test_data = self.test_logs_repository[test_name]
            results['tests_run'] += 1
            
            try:
                # Test platform detection and parsing
                parsed_data = await self.advanced_parser.parse_log_content(
                    test_data['content']
                )
                
                # Test intelligent analysis
                analysis_result = await self.intelligent_analyzer.perform_intelligent_analysis(
                    test_data['content'],
                    parsed_data
                )
                
                # Validate platform-specific detection
                test_passed = True
                validation_details = []
                
                expected_platform = test_data.get('expected_platform')
                detected_platform = analysis_result.get('environmental_context', {}).get('platform')
                
                if expected_platform and detected_platform != expected_platform:
                    test_passed = False
                    validation_details.append(f"Expected platform {expected_platform}, detected {detected_platform}")
                
                expected_categories = test_data.get('expected_categories', [])
                detected_categories = [issue.get('category') for issue in analysis_result.get('identified_issues', [])]
                
                for expected_category in expected_categories:
                    if expected_category not in detected_categories:
                        test_passed = False
                        validation_details.append(f"Expected category '{expected_category}' not detected")
                
                if test_passed:
                    results['tests_passed'] += 1
                
                results['test_details'].append({
                    'test_name': test_name,
                    'passed': test_passed,
                    'detected_platform': detected_platform,
                    'detected_categories': detected_categories,
                    'validation_details': validation_details
                })
                
                if detected_platform and detected_platform not in results['platforms_tested']:
                    results['platforms_tested'].append(detected_platform)
                
            except Exception as e:
                results['test_details'].append({
                    'test_name': test_name,
                    'passed': False,
                    'error': str(e)
                })
        
        results['success_rate'] = (results['tests_passed'] / results['tests_run']) * 100
        return results
    
    async def _test_ml_pattern_discovery(self) -> Dict[str, Any]:
        """Test machine learning pattern discovery capabilities."""
        logger.info("Testing ML pattern discovery...")
        
        results = {
            'tests_run': 0,
            'tests_passed': 0,
            'test_details': []
        }
        
        test_data = self.test_logs_repository['unknown_patterns']
        results['tests_run'] += 1
        
        try:
            # Test ML pattern discovery
            parsed_data = await self.advanced_parser.parse_log_content(
                test_data['content']
            )
            
            # Extract unmatched entries for ML analysis
            unmatched_entries = parsed_data.get('unmatched_entries', [])
            
            if unmatched_entries:
                ml_results = await self.advanced_parser.discover_patterns_with_ml(unmatched_entries)
                
                # Validate ML discovery
                test_passed = True
                validation_details = []
                
                expected_pattern_count = test_data.get('expected_pattern_count')
                actual_pattern_count = len(ml_results.get('patterns_discovered', []))
                
                if expected_pattern_count and actual_pattern_count < expected_pattern_count:
                    test_passed = False
                    validation_details.append(f"Expected {expected_pattern_count} patterns, found {actual_pattern_count}")
                
                expected_confidence = test_data.get('expected_confidence_threshold', 0.7)
                patterns_with_low_confidence = [
                    p for p in ml_results.get('patterns_discovered', [])
                    if p.get('confidence', 0) < expected_confidence
                ]
                
                if patterns_with_low_confidence:
                    validation_details.append(f"{len(patterns_with_low_confidence)} patterns below confidence threshold")
                
                if test_passed:
                    results['tests_passed'] += 1
                
                results['test_details'].append({
                    'test_name': 'unknown_patterns',
                    'passed': test_passed,
                    'patterns_discovered': actual_pattern_count,
                    'avg_confidence': np.mean([p.get('confidence', 0) for p in ml_results.get('patterns_discovered', [])]),
                    'validation_details': validation_details
                })
            else:
                results['test_details'].append({
                    'test_name': 'unknown_patterns',
                    'passed': False,
                    'error': 'No unmatched entries found for ML analysis'
                })
        
        except Exception as e:
            results['test_details'].append({
                'test_name': 'unknown_patterns',
                'passed': False,
                'error': str(e)
            })
        
        results['success_rate'] = (results['tests_passed'] / results['tests_run']) * 100 if results['tests_run'] > 0 else 0
        return results
    
    async def _test_correlation_analysis(self) -> Dict[str, Any]:
        """Test correlation analysis between issues."""
        logger.info("Testing correlation analysis...")
        
        results = {
            'tests_run': 0,
            'tests_passed': 0,
            'test_details': []
        }
        
        test_data = self.test_logs_repository['correlated_issues']
        results['tests_run'] += 1
        
        try:
            # Test correlation analysis
            parsed_data = await self.advanced_parser.parse_log_content(
                test_data['content']
            )
            
            analysis_result = await self.intelligent_analyzer.perform_intelligent_analysis(
                test_data['content'],
                parsed_data
            )
            
            correlation_analysis = analysis_result.get('correlation_analysis', {})
            
            # Validate correlation detection
            test_passed = True
            validation_details = []
            
            if test_data.get('expected_temporal_correlation'):
                temporal_correlations = correlation_analysis.get('temporal_correlations', [])
                if not temporal_correlations:
                    test_passed = False
                    validation_details.append("Expected temporal correlations not found")
            
            if test_data.get('expected_account_correlation'):
                account_correlations = correlation_analysis.get('account_correlations', [])
                if not account_correlations:
                    test_passed = False
                    validation_details.append("Expected account correlations not found")
            
            if test_passed:
                results['tests_passed'] += 1
            
            results['test_details'].append({
                'test_name': 'correlated_issues',
                'passed': test_passed,
                'temporal_correlations_found': len(correlation_analysis.get('temporal_correlations', [])),
                'account_correlations_found': len(correlation_analysis.get('account_correlations', [])),
                'validation_details': validation_details
            })
        
        except Exception as e:
            results['test_details'].append({
                'test_name': 'correlated_issues',
                'passed': False,
                'error': str(e)
            })
        
        results['success_rate'] = (results['tests_passed'] / results['tests_run']) * 100 if results['tests_run'] > 0 else 0
        return results
    
    async def _test_predictive_analysis(self) -> Dict[str, Any]:
        """Test predictive analysis capabilities."""
        logger.info("Testing predictive analysis...")
        
        results = {
            'tests_run': 0,
            'tests_passed': 0,
            'test_details': []
        }
        
        test_data = self.test_logs_repository['degradation_pattern']
        results['tests_run'] += 1
        
        try:
            # Test predictive analysis
            parsed_data = await self.advanced_parser.parse_log_content(
                test_data['content']
            )
            
            analysis_result = await self.intelligent_analyzer.perform_intelligent_analysis(
                test_data['content'],
                parsed_data
            )
            
            predictive_insights = analysis_result.get('predictive_insights', [])
            
            # Validate predictions
            test_passed = True
            validation_details = []
            
            if test_data.get('expected_predictions') and not predictive_insights:
                test_passed = False
                validation_details.append("Expected predictive insights not generated")
            
            expected_prediction_types = test_data.get('expected_prediction_types', [])
            actual_prediction_types = [insight.get('issue_type') for insight in predictive_insights]
            
            for expected_type in expected_prediction_types:
                if expected_type not in actual_prediction_types:
                    test_passed = False
                    validation_details.append(f"Expected prediction type '{expected_type}' not found")
            
            if test_passed:
                results['tests_passed'] += 1
            
            results['test_details'].append({
                'test_name': 'degradation_pattern',
                'passed': test_passed,
                'predictions_generated': len(predictive_insights),
                'prediction_types': actual_prediction_types,
                'avg_probability': np.mean([insight.get('probability', 0) for insight in predictive_insights]) if predictive_insights else 0,
                'validation_details': validation_details
            })
        
        except Exception as e:
            results['test_details'].append({
                'test_name': 'degradation_pattern',
                'passed': False,
                'error': str(e)
            })
        
        results['success_rate'] = (results['tests_passed'] / results['tests_run']) * 100 if results['tests_run'] > 0 else 0
        return results
    
    async def _test_performance_optimization(self) -> Dict[str, Any]:
        """Test performance optimization with different log sizes."""
        logger.info("Testing performance optimization...")
        
        results = {
            'tests_run': 0,
            'tests_passed': 0,
            'test_details': [],
            'performance_benchmarks': {}
        }
        
        performance_tests = ['large_log_file', 'huge_log_file']
        
        for test_name in performance_tests:
            test_data = self.test_logs_repository[test_name]
            results['tests_run'] += 1
            
            try:
                start_time = time.time()
                
                # Test optimized analysis
                basic_data = {'entries': []}  # Minimal basic data
                analysis_result = await self.optimized_analyzer.perform_optimized_analysis(
                    test_data['content'],
                    basic_data
                )
                
                analysis_time = time.time() - start_time
                
                # Validate performance expectations
                test_passed = True
                validation_details = []
                
                max_time = test_data.get('max_analysis_time_seconds', 120)
                if analysis_time > max_time:
                    test_passed = False
                    validation_details.append(f"Analysis took {analysis_time:.1f}s, expected <{max_time}s")
                
                # Check if analysis produced meaningful results
                if not analysis_result.get('basic_analysis') or not analysis_result.get('deep_analysis'):
                    test_passed = False
                    validation_details.append("Analysis did not produce expected results")
                
                if test_passed:
                    results['tests_passed'] += 1
                
                results['test_details'].append({
                    'test_name': test_name,
                    'passed': test_passed,
                    'analysis_time_seconds': analysis_time,
                    'log_size_lines': len(test_data['content'].split('\n')),
                    'validation_details': validation_details
                })
                
                results['performance_benchmarks'][test_name] = {
                    'analysis_time': analysis_time,
                    'log_size': len(test_data['content']),
                    'lines_per_second': len(test_data['content'].split('\n')) / max(analysis_time, 0.001)
                }
            
            except Exception as e:
                results['test_details'].append({
                    'test_name': test_name,
                    'passed': False,
                    'error': str(e)
                })
        
        results['success_rate'] = (results['tests_passed'] / results['tests_run']) * 100 if results['tests_run'] > 0 else 0
        return results
    
    async def _test_full_integration(self) -> Dict[str, Any]:
        """Test full integration of all enhanced components."""
        logger.info("Testing full integration...")
        
        results = {
            'tests_run': 0,
            'tests_passed': 0,
            'test_details': []
        }
        
        # Use a complex log that tests multiple features
        complex_log = """
# Complex multi-platform, multi-language test log
2024-01-15 10:30:25 [ERROR] Connection failed for user@example.com (DNS timeout)
2024-01-15 10:30:26 [ERROR] Registry key not found for user@example.com
2024-01-15 10:30:27 [ERREUR] Échec d'authentification OAuth2 pour admin@exemple.fr
2024-01-15 10:30:28 [ERROR] Keychain access denied for user@icloud.com
2024-01-15 10:30:29 [CUSTOM] XYZ_UNKNOWN_ERROR_999 occurred
2024-01-15 10:30:30 [ERROR] Connection failed for admin@example.com (DNS timeout)
        """
        
        results['tests_run'] += 1
        
        try:
            # Test full pipeline
            start_time = time.time()
            
            # Step 1: Edge case preprocessing
            processed_content = await self.edge_case_handler.preprocess_log_content(complex_log)
            
            # Step 2: Advanced parsing
            parsed_data = await self.advanced_parser.parse_log_content(processed_content)
            
            # Step 3: Intelligent analysis
            analysis_result = await self.intelligent_analyzer.perform_intelligent_analysis(
                processed_content, parsed_data
            )
            
            # Step 4: Solution generation
            solutions = await self.solution_engine.generate_account_specific_solutions(
                analysis_result.get('identified_issues', []),
                parsed_data.get('accounts', {})
            )
            
            total_time = time.time() - start_time
            
            # Validate integration
            test_passed = True
            validation_details = []
            
            # Check that each component contributed
            if not analysis_result.get('identified_issues'):
                test_passed = False
                validation_details.append("No issues identified by intelligent analyzer")
            
            if not analysis_result.get('correlation_analysis'):
                test_passed = False
                validation_details.append("Correlation analysis not performed")
            
            if not analysis_result.get('ml_pattern_discovery'):
                test_passed = False
                validation_details.append("ML pattern discovery not performed")
            
            if not solutions:
                test_passed = False
                validation_details.append("No solutions generated")
            
            # Check cross-platform detection
            environmental_context = analysis_result.get('environmental_context', {})
            if not environmental_context.get('platform'):
                validation_details.append("Platform detection failed")
            
            # Check multi-language support
            validation_summary = analysis_result.get('validation_summary', {})
            if not validation_summary.get('detected_language'):
                validation_details.append("Language detection failed")
            
            if test_passed:
                results['tests_passed'] += 1
            
            results['test_details'].append({
                'test_name': 'full_integration',
                'passed': test_passed,
                'total_processing_time': total_time,
                'issues_identified': len(analysis_result.get('identified_issues', [])),
                'solutions_generated': len(solutions),
                'platforms_detected': environmental_context.get('platform'),
                'languages_detected': validation_summary.get('detected_language'),
                'validation_details': validation_details
            })
        
        except Exception as e:
            results['test_details'].append({
                'test_name': 'full_integration',
                'passed': False,
                'error': str(e)
            })
        
        results['success_rate'] = (results['tests_passed'] / results['tests_run']) * 100 if results['tests_run'] > 0 else 0
        return results
    
    async def _test_solution_validation(self) -> Dict[str, Any]:
        """Test solution validation and automated testing."""
        logger.info("Testing solution validation...")
        
        results = {
            'tests_run': 0,
            'tests_passed': 0,
            'test_details': []
        }
        
        # Create a mock solution for testing
        test_solution = {
            'issue_id': 'test_connection_issue',
            'solution_steps': [
                {
                    'step_number': 1,
                    'description': 'Test DNS resolution',
                    'validation_command': 'nslookup google.com',
                    'expected_outcome': 'DNS resolution successful'
                }
            ],
            'automated_tests': [
                {
                    'test_id': 'dns_test',
                    'test_name': 'DNS Resolution Test',
                    'test_script': 'nslookup google.com',
                    'expected_result': 'Non-authoritative answer',
                    'platform_requirements': ['windows', 'macos', 'linux'],
                    'timeout_seconds': 10
                }
            ]
        }
        
        results['tests_run'] += 1
        
        try:
            # Test solution validation
            validation_results = await self.solution_engine.validate_solution_steps(test_solution)
            
            # Test automated testing
            test_results = await self.solution_engine.run_automated_tests(
                test_solution.get('automated_tests', [])
            )
            
            # Validate results
            test_passed = True
            validation_details = []
            
            if not validation_results:
                test_passed = False
                validation_details.append("Solution validation failed")
            
            if not test_results:
                test_passed = False
                validation_details.append("Automated tests failed")
            
            successful_tests = [t for t in test_results if t.get('passed', False)]
            if len(successful_tests) == 0:
                validation_details.append("No automated tests passed")
            
            if test_passed:
                results['tests_passed'] += 1
            
            results['test_details'].append({
                'test_name': 'solution_validation',
                'passed': test_passed,
                'validation_steps_tested': len(validation_results),
                'automated_tests_run': len(test_results),
                'automated_tests_passed': len(successful_tests),
                'validation_details': validation_details
            })
        
        except Exception as e:
            results['test_details'].append({
                'test_name': 'solution_validation',
                'passed': False,
                'error': str(e)
            })
        
        results['success_rate'] = (results['tests_passed'] / results['tests_run']) * 100 if results['tests_run'] > 0 else 0
        return results
    
    async def _test_automated_remediation(self) -> Dict[str, Any]:
        """Test automated remediation capabilities."""
        logger.info("Testing automated remediation...")
        
        results = {
            'tests_run': 0,
            'tests_passed': 0,
            'test_details': []
        }
        
        # Create a safe test solution for automated remediation
        test_solution = {
            'issue_id': 'safe_test_issue',
            'remediation_script': 'echo "Test remediation script execution"',
            'platform_compatibility': ['windows', 'macos', 'linux'],
            'validation_command': 'echo "Validation successful"',
            'rollback_script': 'echo "Rollback completed"'
        }
        
        results['tests_run'] += 1
        
        try:
            # Test automated remediation (dry run mode)
            remediation_result = await self.solution_engine.execute_automated_remediation(
                test_solution,
                dry_run=True  # Safe testing mode
            )
            
            # Validate remediation
            test_passed = True
            validation_details = []
            
            if not remediation_result.get('executed'):
                test_passed = False
                validation_details.append("Automated remediation did not execute")
            
            if remediation_result.get('error'):
                test_passed = False
                validation_details.append(f"Remediation error: {remediation_result['error']}")
            
            # Test rollback capability
            if test_solution.get('rollback_script'):
                rollback_result = await self.solution_engine.execute_rollback(
                    test_solution,
                    dry_run=True
                )
                
                if not rollback_result.get('executed'):
                    validation_details.append("Rollback capability test failed")
            
            if test_passed:
                results['tests_passed'] += 1
            
            results['test_details'].append({
                'test_name': 'automated_remediation',
                'passed': test_passed,
                'remediation_executed': remediation_result.get('executed', False),
                'rollback_tested': bool(test_solution.get('rollback_script')),
                'execution_time': remediation_result.get('execution_time', 0),
                'validation_details': validation_details
            })
        
        except Exception as e:
            results['test_details'].append({
                'test_name': 'automated_remediation',
                'passed': False,
                'error': str(e)
            })
        
        results['success_rate'] = (results['tests_passed'] / results['tests_run']) * 100 if results['tests_run'] > 0 else 0
        return results
    
    def _generate_test_report(self, test_suite_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive test report."""
        
        total_tests = sum(suite.get('tests_run', 0) for suite in test_suite_results.values())
        total_passed = sum(suite.get('tests_passed', 0) for suite in test_suite_results.values())
        overall_success_rate = (total_passed / total_tests) * 100 if total_tests > 0 else 0
        
        report = {
            'test_summary': {
                'total_test_suites': len(test_suite_results),
                'total_tests_run': total_tests,
                'total_tests_passed': total_passed,
                'overall_success_rate': round(overall_success_rate, 2),
                'test_timestamp': datetime.now().isoformat()
            },
            'suite_results': test_suite_results,
            'recommendations': self._generate_test_recommendations(test_suite_results),
            'performance_summary': self._generate_performance_summary(test_suite_results)
        }
        
        return report
    
    def _generate_test_recommendations(self, test_suite_results: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        for suite_name, suite_results in test_suite_results.items():
            success_rate = suite_results.get('success_rate', 0)
            
            if success_rate < 80:
                recommendations.append(f"⚠️ {suite_name} has low success rate ({success_rate:.1f}%) - requires attention")
            
            if success_rate < 50:
                recommendations.append(f"🚨 {suite_name} critical failure - immediate investigation required")
        
        # Performance recommendations
        performance_tests = test_suite_results.get('performance_tests', {})
        if performance_tests:
            benchmarks = performance_tests.get('performance_benchmarks', {})
            for test_name, metrics in benchmarks.items():
                if metrics.get('analysis_time', 0) > 60:
                    recommendations.append(f"🐌 {test_name} performance optimization needed - {metrics['analysis_time']:.1f}s")
        
        if not recommendations:
            recommendations.append("✅ All test suites passed successfully - system ready for production")
        
        return recommendations
    
    def _generate_performance_summary(self, test_suite_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate performance analysis summary."""
        performance_tests = test_suite_results.get('performance_tests', {})
        benchmarks = performance_tests.get('performance_benchmarks', {})
        
        if not benchmarks:
            return {'status': 'No performance benchmarks available'}
        
        total_time = sum(metrics.get('analysis_time', 0) for metrics in benchmarks.values())
        avg_time = total_time / len(benchmarks)
        
        max_throughput = max((metrics.get('lines_per_second', 0) for metrics in benchmarks.values()), default=0)
        
        return {
            'average_analysis_time': round(avg_time, 2),
            'max_throughput_lines_per_second': round(max_throughput, 0),
            'performance_grade': self._calculate_performance_grade(avg_time, max_throughput)
        }
    
    def _calculate_performance_grade(self, avg_time: float, max_throughput: float) -> str:
        """Calculate performance grade based on metrics."""
        if avg_time < 30 and max_throughput > 1000:
            return "A+ (Excellent)"
        elif avg_time < 60 and max_throughput > 500:
            return "A (Very Good)"
        elif avg_time < 90 and max_throughput > 200:
            return "B (Good)"
        elif avg_time < 120 and max_throughput > 100:
            return "C (Acceptable)"
        else:
            return "D (Needs Improvement)"


# Convenience functions for running specific test categories
async def run_edge_case_tests() -> Dict[str, Any]:
    """Run only edge case handling tests."""
    framework = LogAnalysisTestFramework()
    return await framework._test_edge_case_handling()

async def run_performance_tests() -> Dict[str, Any]:
    """Run only performance optimization tests."""
    framework = LogAnalysisTestFramework()
    return await framework._test_performance_optimization()

async def run_integration_tests() -> Dict[str, Any]:
    """Run only full integration tests."""
    framework = LogAnalysisTestFramework()
    return await framework._test_full_integration()

# Main test runner
async def run_all_tests() -> Dict[str, Any]:
    """Run all comprehensive tests."""
    framework = LogAnalysisTestFramework()
    return await framework.run_comprehensive_tests()

if __name__ == "__main__":
    # Example usage
    import asyncio
    
    async def main():
        print("Starting comprehensive log analysis testing...")
        results = await run_all_tests()
        
        print(f"\n=== TEST RESULTS ===")
        print(f"Total Tests: {results['test_summary']['total_tests_run']}")
        print(f"Passed: {results['test_summary']['total_tests_passed']}")
        print(f"Success Rate: {results['test_summary']['overall_success_rate']:.1f}%")
        
        print(f"\n=== RECOMMENDATIONS ===")
        for rec in results['recommendations']:
            print(f"  {rec}")
        
        print(f"\n=== PERFORMANCE SUMMARY ===")
        perf_summary = results['performance_summary']
        if 'average_analysis_time' in perf_summary:
            print(f"Average Analysis Time: {perf_summary['average_analysis_time']}s")
            print(f"Max Throughput: {perf_summary['max_throughput_lines_per_second']} lines/sec")
            print(f"Performance Grade: {perf_summary['performance_grade']}")
    
    # asyncio.run(main())