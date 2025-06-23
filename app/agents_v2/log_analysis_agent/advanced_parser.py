"""
Advanced Mailbird Log Analysis Engine
Production-grade parser with account-specific analysis and temporal pattern detection.
"""

import re
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import hashlib

class AdvancedMailbirdAnalyzer:
    """
    Advanced log analyzer that provides account-specific analysis, temporal patterns,
    and detailed issue categorization matching the quality of sample reports.
    """
    
    def __init__(self):
        self.accounts = {}  # Track per-account issues
        self.temporal_patterns = []  # Track time-based patterns
        self.issue_correlations = {}  # Track related issues
        
        # Account extraction patterns
        self.account_patterns = [
            re.compile(r"Account:\s*([^|,\s]+)", re.IGNORECASE),
            re.compile(r"Folder:\s*([^,]+),\s*Account:\s*([^|,\s]+)", re.IGNORECASE),
            re.compile(r"([^@\s]+@[^@\s]+\.[^@\s]{2,})", re.IGNORECASE),  # Email addresses
            re.compile(r"User:\s*([^|,\s]+)", re.IGNORECASE),
        ]
        
        # Advanced issue patterns with account correlation
        self.issue_patterns = {
            'imap_push_failure': {
                'patterns': [
                    re.compile(r"Error listening to folder.*Account:\s*([^|,]+)", re.IGNORECASE),
                    re.compile(r"Tried to read a line\. No data received.*Account:\s*([^|,]+)", re.IGNORECASE),
                    re.compile(r"push.*listener.*(?:failed|stopped).*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                ],
                'severity': 'critical',
                'category': 'IMAP Push Listener Failures',
                'impact': 'Reduced real-time email synchronization, increased server polling'
            },
            
            'smtp_send_failure': {
                'patterns': [
                    re.compile(r"Unable to write data to the transport connection.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    re.compile(r"SMTP.*(?:send|transmission).*failed.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    re.compile(r"handshake failed.*unexpected packet format.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                ],
                'severity': 'high',
                'category': 'SMTP Send Failures',
                'impact': 'Failed email sending, messages stuck in drafts'
            },
            
            'message_size_violation': {
                'patterns': [
                    re.compile(r"message exceeded.*size limits.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    re.compile(r"attachment.*too large.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    re.compile(r"Your message exceeded Google's message size limits", re.IGNORECASE),
                ],
                'severity': 'high',
                'category': 'Message Size Limit Violations',
                'impact': 'Failed message delivery, especially with attachments'
            },
            
            'imap_auth_failure': {
                'patterns': [
                    re.compile(r"IMAP server terminating connection.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    re.compile(r"Cannot connect to IMAP server.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    re.compile(r"IMAP.*authentication.*failed.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                ],
                'severity': 'high',
                'category': 'IMAP Authentication Failures',
                'impact': 'Unable to retrieve emails, account disconnection'
            },
            
            'pop3_connection_failure': {
                'patterns': [
                    re.compile(r"Cannot connect to POP server.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    re.compile(r"POP3.*connection.*(?:failed|timeout).*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                ],
                'severity': 'medium',
                'category': 'POP3 Connection Failures',
                'impact': 'Unable to retrieve emails from POP3 server'
            },
            
            'oauth2_failure': {
                'patterns': [
                    re.compile(r"OAuth.*remote name could not be resolved.*accounts\.google\.com", re.IGNORECASE),
                    re.compile(r"OAuth.*remote name could not be resolved.*login\.microsoftonline\.com", re.IGNORECASE),
                    re.compile(r"OAuth.*(?:failed|expired|invalid).*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                ],
                'severity': 'medium',
                'category': 'OAuth2 Authentication Issues',
                'impact': 'Prevents automatic token refresh for Gmail and Outlook accounts'
            },
            
            'power_management_issues': {
                'patterns': [
                    re.compile(r"SystemEvents\.PowerModeChanged:\s*Resume", re.IGNORECASE),
                    re.compile(r"connection.*lost.*after.*(?:resume|wake)", re.IGNORECASE),
                    re.compile(r"suspend.*resume.*connection.*failed", re.IGNORECASE),
                ],
                'severity': 'medium',
                'category': 'Power Management Related Issues',
                'impact': 'Requires manual reconnection after system wake-up'
            },
            
            'dns_resolution_failure': {
                'patterns': [
                    re.compile(r"No such host is known.*([a-zA-Z0-9.-]+)", re.IGNORECASE),
                    re.compile(r"DNS.*resolution.*failed.*([a-zA-Z0-9.-]+)", re.IGNORECASE),
                    re.compile(r"remote name could not be resolved.*([a-zA-Z0-9.-]+)", re.IGNORECASE),
                ],
                'severity': 'medium',
                'category': 'Network/DNS Resolution Problems',
                'impact': 'Temporary connectivity disruptions'
            },
            
            'ssl_handshake_failure': {
                'patterns': [
                    re.compile(r"handshake failed due to an unexpected packet format", re.IGNORECASE),
                    re.compile(r"SSL.*handshake.*failed.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    re.compile(r"TLS.*negotiation.*failed", re.IGNORECASE),
                ],
                'severity': 'medium',
                'category': 'SSL/TLS Handshake Failures',
                'impact': 'SMTP authentication failures'
            },
            
            'connection_drops': {
                'patterns': [
                    re.compile(r"Connection lost \[.*?\]", re.IGNORECASE),
                    re.compile(r"forcibly closed by.*remote host", re.IGNORECASE),
                    re.compile(r"connection.*(?:timeout|dropped|interrupted)", re.IGNORECASE),
                ],
                'severity': 'high',
                'category': 'Frequent Connection Drops',
                'impact': 'Email synchronization interruptions, delayed message delivery'
            },
            
            'exchange_errors': {
                'patterns': [
                    re.compile(r"An item with the same key has already been added.*Exchange", re.IGNORECASE),
                    re.compile(r"Exchange.*search.*error", re.IGNORECASE),
                    re.compile(r"Exchange.*folder.*failed", re.IGNORECASE),
                ],
                'severity': 'medium',
                'category': 'Exchange Search Errors',
                'impact': 'Search functionality degradation'
            }
        }
        
        # System information extraction patterns
        self.system_patterns = {
            'version': [
                re.compile(r"startup\s+\[(\d+\.\d+\.\d+(?:\.\d+)?)\]", re.IGNORECASE),
                re.compile(r"\[(\d+\.\d+\.\d+(?:\.\d+)?)\].*startup", re.IGNORECASE),
                re.compile(r"Mailbird\s+(?:Version\s+)?v?(\d+\.\d+\.\d+(?:\.\d+)?)", re.IGNORECASE),
            ],
            'database_size': [
                re.compile(r"\[Store\.db\s+([\d,\.]+)\s*(KB|MB|GB)\]", re.IGNORECASE),
                re.compile(r"Store\.db\s+([\d,\.]+)\s*(KB|MB|GB)", re.IGNORECASE),
            ],
            'accounts_info': [
                re.compile(r"Accounts:\s*(\d+)", re.IGNORECASE),
                re.compile(r"(\d+)\s+accounts?\s+configured", re.IGNORECASE),
            ],
            'folders_info': [
                re.compile(r"Folders:\s*(\d+)", re.IGNORECASE),
                re.compile(r"(\d+)\s+folders?\s+total", re.IGNORECASE),
            ],
            'exchange_version': [
                re.compile(r"Exchange.*Server.*Version.*(\d+\.\d+\.\d+\.\d+)", re.IGNORECASE),
                re.compile(r"Exchange.*(\d+\.\d+\.\d+\.\d+)", re.IGNORECASE),
            ]
        }

    def analyze_logs(self, raw_log_content: str) -> Dict[str, Any]:
        """
        Perform comprehensive log analysis with account-specific tracking and temporal patterns.
        """
        lines = raw_log_content.strip().split('\n')
        
        # Parse each line and extract detailed information
        parsed_entries = []
        account_issues = defaultdict(list)
        temporal_events = []
        positive_observations = []
        
        for line_num, line in enumerate(lines, 1):
            entry = self._parse_log_line(line, line_num)
            if entry:
                parsed_entries.append(entry)
                
                # Track account-specific issues
                if entry.get('account') and entry.get('issue_type'):
                    account_issues[entry['account']].append(entry)
                
                # Track temporal patterns
                if entry.get('timestamp'):
                    temporal_events.append(entry)
                
                # Track positive observations
                if entry.get('status') == 'success':
                    positive_observations.append(entry)
        
        # Extract system information
        system_profile = self._extract_system_info(raw_log_content)
        
        # Analyze account-specific patterns
        account_analysis = self._analyze_account_patterns(account_issues)
        
        # Detect temporal correlations
        temporal_analysis = self._analyze_temporal_patterns(temporal_events)
        
        # Generate comprehensive issues list
        detected_issues = self._generate_comprehensive_issues(account_issues, temporal_analysis)
        
        # Analyze positive patterns
        positive_analysis = self._analyze_positive_patterns(positive_observations)
        
        return {
            'entries': parsed_entries,
            'system_profile': system_profile,
            'detected_issues': detected_issues,
            'account_analysis': account_analysis,
            'temporal_analysis': temporal_analysis,
            'positive_observations': positive_analysis,
            'metadata': {
                'total_entries_parsed': len(parsed_entries),
                'unique_accounts': len(account_issues),
                'error_rate_percentage': self._calculate_error_rate(parsed_entries),
                'log_timeframe': self._extract_timeframe(parsed_entries),
                'analysis_timestamp': datetime.utcnow().isoformat()
            }
        }

    def _parse_log_line(self, line: str, line_num: int) -> Optional[Dict[str, Any]]:
        """Parse individual log line with comprehensive pattern matching."""
        if not line.strip():
            return None
            
        entry = {
            'line_number': line_num,
            'raw_content': line,
            'timestamp': self._extract_timestamp(line),
            'log_level': self._extract_log_level(line),
            'account': None,
            'issue_type': None,
            'severity': 'info',
            'status': 'unknown'
        }
        
        # Extract account information
        entry['account'] = self._extract_account(line)
        
        # Detect issue patterns
        for issue_type, config in self.issue_patterns.items():
            for pattern in config['patterns']:
                match = pattern.search(line)
                if match:
                    entry['issue_type'] = issue_type
                    entry['severity'] = config['severity']
                    entry['category'] = config['category']
                    entry['impact'] = config['impact']
                    entry['status'] = 'error'
                    
                    # Extract additional context from match groups
                    try:
                        if match.groups() and len(match.groups()) > 0:
                            entry['extracted_account'] = match.group(1)
                    except (IndexError, AttributeError):
                        # If group access fails, use the account from _extract_account
                        entry['extracted_account'] = entry.get('account')
                    break
            if entry['issue_type']:
                break
        
        # Detect success patterns
        if any(keyword in line.lower() for keyword in ['success', 'connected', 'authenticated', 'sync complete']):
            entry['status'] = 'success'
        
        return entry

    def _extract_account(self, line: str) -> Optional[str]:
        """Extract account information from log line."""
        for pattern in self.account_patterns:
            match = pattern.search(line)
            if match:
                try:
                    # Check if there are capture groups
                    if match.groups():
                        # Return the last non-empty capture group
                        for i in range(len(match.groups()), 0, -1):
                            group_value = match.group(i)
                            if group_value and group_value.strip():
                                return group_value.strip()
                    # If no capture groups or all are empty, return the full match
                    full_match = match.group(0)
                    if full_match and full_match.strip():
                        return full_match.strip()
                except (IndexError, AttributeError):
                    # If group access fails, try to extract email pattern from the line
                    email_pattern = re.compile(r'([^@\s]+@[^@\s]+\.[^@\s]{2,})', re.IGNORECASE)
                    email_match = email_pattern.search(line)
                    if email_match:
                        return email_match.group(1).strip()
        return None

    def _extract_timestamp(self, line: str) -> Optional[str]:
        """Extract timestamp from log line."""
        timestamp_patterns = [
            re.compile(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[.\d]*)", re.IGNORECASE),
            re.compile(r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})", re.IGNORECASE),
        ]
        
        for pattern in timestamp_patterns:
            match = pattern.search(line)
            if match:
                return match.group(1)
        return None

    def _extract_log_level(self, line: str) -> str:
        """Extract log level from line."""
        levels = ['ERROR', 'WARNING', 'WARN', 'INFO', 'DEBUG', 'TRACE']
        for level in levels:
            if level in line.upper():
                return level
        return 'INFO'

    def _extract_system_info(self, raw_content: str) -> Dict[str, Any]:
        """Extract comprehensive system information."""
        system_info = {
            'mailbird_version': 'Unknown',
            'database_size_mb': 0.0,
            'account_count': 0,
            'folder_count': 0,
            'exchange_version': None,
            'providers_detected': []
        }
        
        for info_type, patterns in self.system_patterns.items():
            for pattern in patterns:
                match = pattern.search(raw_content)
                if match:
                    try:
                        if info_type == 'version' and match.groups():
                            system_info['mailbird_version'] = match.group(1)
                        elif info_type == 'database_size' and len(match.groups()) >= 2:
                            size_val = float(match.group(1).replace(',', '.'))
                            unit = match.group(2).upper()
                            if unit == 'GB':
                                size_val *= 1024
                            elif unit == 'KB':
                                size_val /= 1024
                            system_info['database_size_mb'] = size_val
                        elif info_type == 'accounts_info' and match.groups():
                            system_info['account_count'] = int(match.group(1))
                        elif info_type == 'folders_info' and match.groups():
                            system_info['folder_count'] = int(match.group(1))
                        elif info_type == 'exchange_version' and match.groups():
                            system_info['exchange_version'] = match.group(1)
                        break
                    except (IndexError, ValueError, AttributeError) as e:
                        # Log the error but continue processing
                        print(f"Error processing {info_type} pattern: {e}")
                        continue
        
        # Detect email providers
        providers = ['Gmail', 'Outlook', 'Yahoo', 'Exchange', 'IMAP', 'POP3']
        for provider in providers:
            if provider.lower() in raw_content.lower():
                system_info['providers_detected'].append(provider)
        
        return system_info

    def _analyze_account_patterns(self, account_issues: Dict[str, List]) -> List[Dict[str, Any]]:
        """Analyze patterns per account."""
        account_analysis = []
        
        for account, issues in account_issues.items():
            if not account:
                continue
                
            issue_types = Counter([issue['issue_type'] for issue in issues if issue.get('issue_type')])
            severity_counts = Counter([issue['severity'] for issue in issues])
            
            # Determine account status
            status = 'stable'
            if severity_counts.get('critical', 0) > 0:
                status = 'non-functional'
            elif severity_counts.get('high', 0) > 2:
                status = 'major issues'
            elif severity_counts.get('high', 0) > 0 or severity_counts.get('medium', 0) > 3:
                status = 'intermittent issues'
            elif severity_counts.get('medium', 0) > 0:
                status = 'minor issues'
            
            account_analysis.append({
                'account': account,
                'total_issues': len(issues),
                'issue_types': dict(issue_types),
                'severity_breakdown': dict(severity_counts),
                'status': status,
                'primary_issues': list(issue_types.most_common(3))
            })
        
        return sorted(account_analysis, key=lambda x: x['total_issues'], reverse=True)

    def _analyze_temporal_patterns(self, temporal_events: List[Dict]) -> Dict[str, Any]:
        """Analyze time-based patterns in issues."""
        # This would analyze patterns like "connection drops after power resume"
        power_resume_pattern = []
        peak_error_times = []
        
        for event in temporal_events:
            if event.get('issue_type') == 'power_management_issues':
                power_resume_pattern.append(event)
        
        return {
            'power_management_correlations': len(power_resume_pattern),
            'peak_error_periods': peak_error_times,
            'pattern_analysis': 'Connection issues correlate with system power events' if power_resume_pattern else None
        }

    def _analyze_positive_patterns(self, positive_events: List[Dict]) -> Dict[str, Any]:
        """Analyze what's working well."""
        if not positive_events:
            return {}
        
        success_by_type = Counter([event.get('category', 'unknown') for event in positive_events])
        
        return {
            'successful_operations': len(positive_events),
            'success_categories': dict(success_by_type),
            'stability_indicators': [
                f"{category}: {count} successful operations" 
                for category, count in success_by_type.most_common(3)
            ]
        }

    def _generate_comprehensive_issues(self, account_issues: Dict, temporal_analysis: Dict) -> List[Dict[str, Any]]:
        """Generate detailed issues with proper categorization."""
        comprehensive_issues = []
        
        # Aggregate issues by type across all accounts
        issue_aggregation = defaultdict(lambda: {
            'accounts_affected': set(),
            'total_occurrences': 0,
            'severity': 'low',
            'category': 'Unknown',
            'impact': 'Unknown impact',
            'first_seen': None,
            'last_seen': None
        })
        
        for account, issues in account_issues.items():
            for issue in issues:
                issue_type = issue.get('issue_type')
                if not issue_type:
                    continue
                    
                agg = issue_aggregation[issue_type]
                agg['accounts_affected'].add(account)
                agg['total_occurrences'] += 1
                
                # Update metadata from issue patterns
                if issue_type in self.issue_patterns:
                    config = self.issue_patterns[issue_type]
                    agg['severity'] = config['severity']
                    agg['category'] = config['category']
                    agg['impact'] = config['impact']
                
                # Track timing
                timestamp = issue.get('timestamp')
                if timestamp:
                    if not agg['first_seen'] or timestamp < agg['first_seen']:
                        agg['first_seen'] = timestamp
                    if not agg['last_seen'] or timestamp > agg['last_seen']:
                        agg['last_seen'] = timestamp
        
        # Convert to final format
        for issue_type, data in issue_aggregation.items():
            issue_id = hashlib.md5(f"{issue_type}_{','.join(sorted(data['accounts_affected']))}".encode()).hexdigest()[:6]
            
            comprehensive_issues.append({
                'issue_id': f"{issue_type}_{issue_id}",
                'category': data['category'],
                'signature': issue_type.replace('_', ' ').title(),
                'occurrences': data['total_occurrences'],
                'severity': data['severity'].title(),
                'root_cause': self._generate_root_cause_analysis(issue_type, data),
                'user_impact': data['impact'],
                'affected_accounts': list(data['accounts_affected']),
                'first_occurrence': data['first_seen'],
                'last_occurrence': data['last_seen'],
                'frequency_pattern': self._analyze_frequency_pattern(data),
                'related_log_levels': ['ERROR', 'WARNING'],
                'confidence_score': 0.9  # High confidence for pattern-matched issues
            })
        
        return sorted(comprehensive_issues, key=lambda x: self._severity_score(x['severity']), reverse=True)

    def _generate_root_cause_analysis(self, issue_type: str, data: Dict) -> str:
        """Generate detailed root cause analysis."""
        root_causes = {
            'imap_push_failure': 'IMAP push listeners failing due to server-side connection limits or network instability',
            'smtp_send_failure': 'SMTP server configuration issues, authentication problems, or network connectivity',
            'message_size_violation': 'Email attachments exceeding provider limits (Gmail: 25MB, Outlook: 20MB)',
            'imap_auth_failure': 'Incorrect server settings, expired passwords, or server-side authentication issues',
            'oauth2_failure': 'DNS resolution problems preventing OAuth2 token refresh with provider servers',
            'power_management_issues': 'Network adapter power saving features disrupting connections during system resume',
            'connection_drops': 'Network infrastructure issues, firewall blocking, or ISP connectivity problems',
            'ssl_handshake_failure': 'SSL/TLS protocol mismatch between client and server configurations'
        }
        
        return root_causes.get(issue_type, f"Technical issue in {issue_type.replace('_', ' ')} functionality")

    def _analyze_frequency_pattern(self, data: Dict) -> str:
        """Analyze issue frequency patterns."""
        total = data['total_occurrences']
        if total > 10:
            return "High frequency - multiple daily occurrences"
        elif total > 5:
            return "Moderate frequency - several occurrences per day"
        elif total > 1:
            return "Low frequency - occasional occurrences"
        else:
            return "Single occurrence"

    def _severity_score(self, severity: str) -> int:
        """Convert severity to numeric score for sorting."""
        scores = {'Critical': 4, 'High': 3, 'Medium': 2, 'Low': 1}
        return scores.get(severity, 0)

    def _calculate_error_rate(self, entries: List[Dict]) -> float:
        """Calculate error rate percentage."""
        if not entries:
            return 0.0
        
        error_count = sum(1 for entry in entries if entry.get('status') == 'error')
        return round((error_count / len(entries)) * 100, 2)

    def _extract_timeframe(self, entries: List[Dict]) -> str:
        """Extract log timeframe from entries."""
        timestamps = [entry.get('timestamp') for entry in entries if entry.get('timestamp')]
        if not timestamps:
            return "Unknown"
        
        return f"{min(timestamps)} to {max(timestamps)}"


def enhanced_parse_log_content(raw_log_content: str) -> Dict[str, Any]:
    """
    Main entry point for enhanced log parsing with comprehensive analysis.
    """
    analyzer = AdvancedMailbirdAnalyzer()
    return analyzer.analyze_logs(raw_log_content)