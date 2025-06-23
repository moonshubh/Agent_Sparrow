"""
Enhanced Mailbird Log Parser with Deep System Profiling
Designed for production-grade log analysis with comprehensive metadata extraction.
"""

import re
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import hashlib

class MailbirdSystemProfiler:
    """Advanced system profiler for extracting detailed Mailbird system information."""
    
    def __init__(self):
        # Enhanced regex patterns for comprehensive metadata extraction
        self.patterns = {
            'version': [
                # Mailbird specific format: [3.0.39.0] in startup line
                re.compile(r"startup\s+\[(\d+\.\d+\.\d+(?:\.\d+)?)\]", re.IGNORECASE),
                re.compile(r"\[(\d+\.\d+\.\d+(?:\.\d+)?)\].*startup", re.IGNORECASE),
                # Generic fallback patterns
                re.compile(r"Mailbird\s+(?:Version\s+)?v?(\d+\.\d+\.\d+(?:\.\d+)?)", re.IGNORECASE),
                re.compile(r"Build\s+(\d+\.\d+\.\d+(?:\.\d+)?)", re.IGNORECASE),
                re.compile(r"Version:\s*(\d+\.\d+\.\d+(?:\.\d+)?)", re.IGNORECASE),
            ],
            'database_size': [
                # Mailbird specific format: [Store.db 1,27 GB]
                re.compile(r"\[Store\.db\s+([\d,\.]+)\s*(KB|MB|GB)\]", re.IGNORECASE),
                re.compile(r"Store\.db\s+([\d,\.]+)\s*(KB|MB|GB)", re.IGNORECASE),
                # Generic fallback patterns
                re.compile(r"Database\s+size\s*[:=]\s*([\d,\.]+)\s*(KB|MB|GB)", re.IGNORECASE),
                re.compile(r"DB\s+Size\s*[:=]\s*([\d,\.]+)\s*(KB|MB|GB)", re.IGNORECASE),
                re.compile(r"mailbird\.db.*?(\d+(?:\.\d+)?)\s*(KB|MB|GB)", re.IGNORECASE),
            ],
            'accounts': [
                re.compile(r"(?:Total\s+)?Accounts?\s*[:=]\s*(\d+)", re.IGNORECASE),
                re.compile(r"(\d+)\s+accounts?\s+configured", re.IGNORECASE),
                re.compile(r"Account\s+count\s*[:=]\s*(\d+)", re.IGNORECASE),
            ],
            'folders': [
                re.compile(r"(?:Total\s+)?Folders?\s*[:=]\s*(\d+)", re.IGNORECASE),
                re.compile(r"(\d+)\s+folders?\s+total", re.IGNORECASE),
                re.compile(r"Folder\s+count\s*[:=]\s*(\d+)", re.IGNORECASE),
            ],
            'memory_usage': [
                re.compile(r"Memory\s+usage\s*[:=]\s*([\d,\.]+)\s*(KB|MB|GB)", re.IGNORECASE),
                re.compile(r"Working\s+set\s*[:=]\s*([\d,\.]+)\s*(KB|MB|GB)", re.IGNORECASE),
            ],
            'startup_time': [
                re.compile(r"Startup\s+time\s*[:=]\s*([\d,\.]+)\s*(?:ms|seconds?)", re.IGNORECASE),
                re.compile(r"Application\s+loaded\s+in\s+([\d,\.]+)\s*(?:ms|seconds?)", re.IGNORECASE),
            ],
            'email_providers': [
                re.compile(r"(Gmail|Outlook|Yahoo|IMAP|Exchange|POP3)", re.IGNORECASE),
            ],
            'sync_status': [
                re.compile(r"Sync\s+(?:status|state)\s*[:=]\s*(\w+)", re.IGNORECASE),
                re.compile(r"Last\s+sync\s*[:=]\s*([^|]+)", re.IGNORECASE),
            ]
        }
        
        # Critical error patterns for advanced issue detection
        self.error_patterns = {
            'database_corruption': [
                re.compile(r"(?:database|db)\s+(?:corruption|corrupt|locked)", re.IGNORECASE),
                re.compile(r"SqliteException", re.IGNORECASE),
                re.compile(r"database\s+is\s+locked", re.IGNORECASE),
            ],
            'authentication_failure': [
                re.compile(r"authentication\s+(?:failed|error)", re.IGNORECASE),
                re.compile(r"oauth\s+(?:failed|error|expired)", re.IGNORECASE),
                re.compile(r"login\s+(?:failed|denied)", re.IGNORECASE),
                re.compile(r"invalid\s+(?:credentials|password)", re.IGNORECASE),
            ],
            'network_connectivity': [
                # Mailbird specific network errors from actual logs
                re.compile(r"Tried to read a line\. No data received", re.IGNORECASE),
                re.compile(r"Error listening to folder", re.IGNORECASE),
                re.compile(r"Connection lost \[.*?\]", re.IGNORECASE),
                re.compile(r"Error in client close method", re.IGNORECASE),
                re.compile(r"Limilabs\.Client\.ServerException", re.IGNORECASE),
                re.compile(r"The stream could not be read", re.IGNORECASE),
                # Generic network patterns
                re.compile(r"SocketException", re.IGNORECASE),
                re.compile(r"connection\s+(?:timeout|refused|failed)", re.IGNORECASE),
                re.compile(r"network\s+(?:error|unreachable)", re.IGNORECASE),
                re.compile(r"dns\s+(?:resolution|lookup)\s+failed", re.IGNORECASE),
            ],
            'sync_issues': [
                re.compile(r"sync\s+(?:failed|error|timeout)", re.IGNORECASE),
                re.compile(r"unable\s+to\s+sync", re.IGNORECASE),
                re.compile(r"synchronization\s+error", re.IGNORECASE),
            ],
            'memory_issues': [
                re.compile(r"out\s+of\s+memory", re.IGNORECASE),
                re.compile(r"memory\s+(?:leak|exhausted)", re.IGNORECASE),
                re.compile(r"OutOfMemoryException", re.IGNORECASE),
            ],
            'attachment_issues': [
                re.compile(r"attachment\s+(?:failed|error|corrupt)", re.IGNORECASE),
                re.compile(r"unable\s+to\s+(?:download|open)\s+attachment", re.IGNORECASE),
            ],
            'ui_performance': [
                re.compile(r"ui\s+(?:freeze|hanging|not\s+responding)", re.IGNORECASE),
                re.compile(r"application\s+(?:freeze|hang)", re.IGNORECASE),
                re.compile(r"slow\s+(?:performance|response)", re.IGNORECASE),
            ]
        }
    
    def extract_system_metadata(self, log_content: str) -> Dict[str, Any]:
        """Extract comprehensive system metadata from log content."""
        lines = log_content.split('\n')
        metadata = {
            'mailbird_version': None,
            'database_size_mb': None,
            'account_count': None,
            'folder_count': None,
            'memory_usage_mb': None,
            'startup_time_ms': None,
            'email_providers': [],
            'sync_status': None,
            'system_architecture': None,
            'os_version': None,
        }
        
        for line in lines:
            # Extract version information
            if not metadata['mailbird_version']:
                for pattern in self.patterns['version']:
                    match = pattern.search(line)
                    if match:
                        metadata['mailbird_version'] = match.group(1)
                        break
            
            # Extract database size
            if not metadata['database_size_mb']:
                for pattern in self.patterns['database_size']:
                    match = pattern.search(line)
                    if match:
                        size_val = float(match.group(1).replace(',', ''))
                        unit = match.group(2).upper()
                        if unit == 'KB':
                            size_val /= 1024
                        elif unit == 'GB':
                            size_val *= 1024
                        metadata['database_size_mb'] = round(size_val, 2)
                        break
            
            # Extract account count
            if not metadata['account_count']:
                for pattern in self.patterns['accounts']:
                    match = pattern.search(line)
                    if match:
                        metadata['account_count'] = int(match.group(1))
                        break
            
            # Extract folder count
            if not metadata['folder_count']:
                for pattern in self.patterns['folders']:
                    match = pattern.search(line)
                    if match:
                        metadata['folder_count'] = int(match.group(1))
                        break
            
            # Extract memory usage
            if not metadata['memory_usage_mb']:
                for pattern in self.patterns['memory_usage']:
                    match = pattern.search(line)
                    if match:
                        memory_val = float(match.group(1).replace(',', ''))
                        unit = match.group(2).upper()
                        if unit == 'KB':
                            memory_val /= 1024
                        elif unit == 'GB':
                            memory_val *= 1024
                        metadata['memory_usage_mb'] = round(memory_val, 2)
                        break
            
            # Extract email providers
            for pattern in self.patterns['email_providers']:
                matches = pattern.findall(line)
                for match in matches:
                    if match.lower() not in [p.lower() for p in metadata['email_providers']]:
                        metadata['email_providers'].append(match)
            
            # Extract system info
            if 'Windows' in line and not metadata['os_version']:
                win_match = re.search(r'Windows\s+(\d+(?:\.\d+)?)', line, re.IGNORECASE)
                if win_match:
                    metadata['os_version'] = f"Windows {win_match.group(1)}"
            
            if 'x64' in line and not metadata['system_architecture']:
                metadata['system_architecture'] = 'x64'
            elif 'x86' in line and not metadata['system_architecture']:
                metadata['system_architecture'] = 'x86'
        
        # Set defaults for missing values
        for key, value in metadata.items():
            if value is None:
                if key in ['account_count', 'folder_count']:
                    metadata[key] = 0
                else:
                    metadata[key] = 'Unknown'
        
        return metadata
    
    def detect_issues(self, log_entries: List[Dict]) -> List[Dict[str, Any]]:
        """Advanced issue detection with pattern recognition and severity assessment."""
        detected_issues = []
        error_counter = Counter()
        timestamp_errors = defaultdict(list)
        
        for entry in log_entries:
            full_message = f"{entry.get('message', '')} {entry.get('details', '')}"
            timestamp = entry.get('timestamp')
            level = entry.get('level', '').upper()
            
            # Check against each error pattern category
            for issue_type, patterns in self.error_patterns.items():
                for pattern in patterns:
                    matches = pattern.findall(full_message)
                    if matches:
                        error_key = f"{issue_type}:{pattern.pattern[:50]}"
                        error_counter[error_key] += len(matches)
                        if timestamp:
                            timestamp_errors[error_key].append(timestamp)
        
        # Process detected error patterns into structured issues
        for error_key, count in error_counter.items():
            issue_type, pattern_sample = error_key.split(':', 1)
            
            # Determine severity based on frequency and error type
            severity = self._calculate_severity(issue_type, count, len(log_entries))
            
            # Extract timestamps
            timestamps = timestamp_errors[error_key]
            first_occurrence = min(timestamps) if timestamps else None
            last_occurrence = max(timestamps) if timestamps else None
            
            # Generate issue metadata
            issue = {
                'issue_id': self._generate_issue_id(issue_type, pattern_sample),
                'category': issue_type,
                'signature': pattern_sample,
                'occurrences': count,
                'severity': severity,
                'root_cause': self._infer_root_cause(issue_type, count),
                'user_impact': self._assess_user_impact(issue_type, severity),
                'first_occurrence': first_occurrence,
                'last_occurrence': last_occurrence,
                'frequency_pattern': self._analyze_frequency_pattern(timestamps),
                'related_log_levels': self._get_related_log_levels(log_entries, issue_type)
            }
            
            detected_issues.append(issue)
        
        # Sort by severity and frequency
        detected_issues.sort(key=lambda x: (
            {'High': 3, 'Medium': 2, 'Low': 1}[x['severity']],
            x['occurrences']
        ), reverse=True)
        
        return detected_issues
    
    def _calculate_severity(self, issue_type: str, count: int, total_entries: int) -> str:
        """Calculate issue severity based on type, frequency, and context."""
        frequency_ratio = count / max(total_entries, 1)
        
        # High-impact issue types
        critical_types = ['database_corruption', 'authentication_failure', 'memory_issues']
        if issue_type in critical_types:
            return 'High' if count > 1 else 'Medium'
        
        # Medium-impact issue types
        moderate_types = ['network_connectivity', 'sync_issues', 'ui_performance']
        if issue_type in moderate_types:
            if frequency_ratio > 0.1 or count > 10:
                return 'High'
            elif frequency_ratio > 0.05 or count > 5:
                return 'Medium'
            else:
                return 'Low'
        
        # Low-impact or informational
        if frequency_ratio > 0.2:
            return 'Medium'
        else:
            return 'Low'
    
    def _generate_issue_id(self, issue_type: str, pattern: str) -> str:
        """Generate a unique, descriptive issue ID."""
        # Create a short hash for uniqueness
        hash_obj = hashlib.md5(f"{issue_type}:{pattern}".encode())
        hash_short = hash_obj.hexdigest()[:6]
        return f"{issue_type}_{hash_short}"
    
    def _infer_root_cause(self, issue_type: str, count: int) -> str:
        """Infer the most likely root cause based on issue type and frequency."""
        root_causes = {
            'database_corruption': "Database file corruption due to improper shutdown, disk errors, or concurrent access issues",
            'authentication_failure': "Expired OAuth tokens, incorrect credentials, or server-side authentication policy changes",
            'network_connectivity': "Network infrastructure issues, firewall blocking, DNS resolution problems, or ISP connectivity",
            'sync_issues': "Server synchronization conflicts, account configuration errors, or rate limiting",
            'memory_issues': "Memory leaks in application code, excessive data caching, or insufficient system resources",
            'attachment_issues': "File permission problems, antivirus interference, or corrupted attachment data",
            'ui_performance': "Resource contention, excessive background processing, or UI thread blocking operations"
        }
        
        base_cause = root_causes.get(issue_type, "Undetermined cause requiring further analysis")
        
        if count > 20:
            base_cause += " (High frequency suggests persistent underlying issue)"
        elif count > 5:
            base_cause += " (Moderate frequency indicates intermittent problem)"
        
        return base_cause
    
    def _assess_user_impact(self, issue_type: str, severity: str) -> str:
        """Assess the user-facing impact of the issue."""
        impacts = {
            'database_corruption': {
                'High': "Complete data loss risk, application crashes, inability to access emails",
                'Medium': "Intermittent data access issues, occasional crashes, sync problems",
                'Low': "Minor data inconsistencies, rare application hiccups"
            },
            'authentication_failure': {
                'High': "Cannot access email accounts, complete email functionality loss",
                'Medium': "Intermittent email access issues, manual re-authentication required",
                'Low': "Occasional authentication prompts, minor sync delays"
            },
            'network_connectivity': {
                'High': "No email synchronization, unable to send/receive emails",
                'Medium': "Delayed email delivery, intermittent sync failures",
                'Low': "Occasional connection timeouts, minor sync delays"
            },
            'sync_issues': {
                'High': "Emails not updating, missing recent messages, sync completely broken",
                'Medium': "Delayed email updates, inconsistent folder synchronization",
                'Low': "Minor sync delays, occasional missed updates"
            },
            'memory_issues': {
                'High': "Application crashes, system slowdown, potential data loss",
                'Medium': "Reduced performance, occasional freezing, high memory usage",
                'Low': "Minor performance impact, slightly increased memory consumption"
            },
            'attachment_issues': {
                'High': "Cannot open or download attachments, attachment functionality broken",
                'Medium': "Intermittent attachment problems, some files inaccessible",
                'Low': "Occasional attachment delays, minor file access issues"
            },
            'ui_performance': {
                'High': "Application frequently unresponsive, severe usability impact",
                'Medium': "Noticeable UI delays, occasional freezing during operations",
                'Low': "Minor performance impact, slightly slower response times"
            }
        }
        
        return impacts.get(issue_type, {}).get(severity, "Impact assessment requires further analysis")
    
    def _analyze_frequency_pattern(self, timestamps: List[str]) -> str:
        """Analyze the temporal pattern of error occurrences."""
        if not timestamps or len(timestamps) < 2:
            return "Insufficient data for pattern analysis"
        
        try:
            # Parse timestamps and calculate intervals
            dt_objects = [datetime.strptime(ts, "%Y-%m-%d %H:%M:%S.%f") for ts in timestamps]
            dt_objects.sort()
            
            intervals = [(dt_objects[i+1] - dt_objects[i]).total_seconds() for i in range(len(dt_objects)-1)]
            avg_interval = sum(intervals) / len(intervals)
            
            if avg_interval < 60:  # Less than 1 minute
                return "High frequency bursts (sub-minute intervals)"
            elif avg_interval < 3600:  # Less than 1 hour
                return "Regular occurrence (minute-level intervals)"
            elif avg_interval < 86400:  # Less than 1 day
                return "Periodic occurrence (hourly intervals)"
            else:
                return "Infrequent occurrence (daily+ intervals)"
                
        except Exception:
            return "Pattern analysis failed due to timestamp format issues"
    
    def _get_related_log_levels(self, log_entries: List[Dict], issue_type: str) -> List[str]:
        """Get the log levels associated with this issue type."""
        levels = set()
        
        for entry in log_entries:
            full_message = f"{entry.get('message', '')} {entry.get('details', '')}"
            level = entry.get('level', '').upper()
            
            # Check if this entry relates to the issue type
            patterns = self.error_patterns.get(issue_type, [])
            for pattern in patterns:
                if pattern.search(full_message):
                    levels.add(level)
                    break
        
        return sorted(list(levels))


def enhanced_parse_log_content(log_content: str) -> Dict[str, Any]:
    """
    Enhanced log parsing with comprehensive system profiling and issue detection.
    """
    profiler = MailbirdSystemProfiler()
    
    # Basic log entry parsing (reuse existing logic but enhanced)
    LOG_START_PATTERN = re.compile(
        r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.\d{4})\|"
        r"(?P<level>[A-Z]+)\|"
        r"(?P<thread_id>\d+)\|"
        r"(?P<source_info_1>\d+)\|"
        r"(?P<source_info_2>\d+)\|"
        r"(?P<message>.*?)(?=\||$)"
    )
    
    raw_lines = log_content.strip().split('\n')
    structured_entries = []
    current_entry_dict = None
    
    for line in raw_lines:
        match = LOG_START_PATTERN.match(line)
        if match:
            if current_entry_dict:
                structured_entries.append(current_entry_dict)
            data = match.groupdict()
            current_entry_dict = {
                "timestamp": data.get("timestamp"),
                "level": data.get("level"),
                "thread_id": data.get("thread_id"),
                "message": data.get("message", "").strip(),
                "details": []
            }
        elif current_entry_dict:
            current_entry_dict["details"].append(line.strip())
    
    if current_entry_dict:
        structured_entries.append(current_entry_dict)
    
    # Join details for easier processing
    for entry in structured_entries:
        entry["details"] = "\n".join(entry["details"])
    
    # Extract comprehensive system metadata
    system_metadata = profiler.extract_system_metadata(log_content)
    
    # Detect issues with advanced pattern recognition
    detected_issues = profiler.detect_issues(structured_entries)
    
    # Calculate log timeframe
    log_timeframe = "Unknown"
    if structured_entries:
        try:
            timestamps = [
                datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S.%f")
                for entry in structured_entries if entry.get("timestamp")
            ]
            if timestamps:
                min_ts = min(timestamps)
                max_ts = max(timestamps)
                log_timeframe = f"{min_ts.strftime('%Y-%m-%d %H:%M:%S')} to {max_ts.strftime('%Y-%m-%d %H:%M:%S')}"
        except Exception:
            log_timeframe = "Invalid timestamp format"
    
    # Compile comprehensive metadata
    enhanced_metadata = {
        **system_metadata,
        "total_lines_processed": len(raw_lines),
        "total_entries_parsed": len(structured_entries),
        "analysis_timestamp": datetime.utcnow().isoformat(),
        "parser_version": "3.0.0-enhanced",
        "parser_notes": "Enhanced Mailbird log parser with deep system profiling and issue detection",
        "log_timeframe": log_timeframe,
        "detected_issue_count": len(detected_issues),
        "log_level_distribution": _calculate_log_level_distribution(structured_entries),
        "error_rate_percentage": _calculate_error_rate(structured_entries),
    }
    
    return {
        "entries": structured_entries,
        "metadata": enhanced_metadata,
        "detected_issues": detected_issues,
        "system_profile": system_metadata
    }


def _calculate_log_level_distribution(entries: List[Dict]) -> Dict[str, int]:
    """Calculate distribution of log levels."""
    distribution = Counter()
    for entry in entries:
        level = entry.get('level', 'UNKNOWN').upper()
        distribution[level] += 1
    return dict(distribution)


def _calculate_error_rate(entries: List[Dict]) -> float:
    """Calculate the percentage of error/warning entries."""
    if not entries:
        return 0.0
    
    error_levels = {'ERROR', 'FATAL', 'CRITICAL', 'WARNING', 'WARN'}
    error_count = sum(1 for entry in entries if entry.get('level', '').upper() in error_levels)
    
    return round((error_count / len(entries)) * 100, 2)