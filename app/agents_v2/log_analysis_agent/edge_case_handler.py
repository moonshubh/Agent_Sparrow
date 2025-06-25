"""
Comprehensive edge case handling for log analysis.
Handles various input formats, encodings, corrupted data, and edge cases.
"""

from typing import Dict, Any, List, Optional, Tuple, Union
import chardet
import zlib
import base64
import re
import json
from datetime import datetime, timezone
import asyncio
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class EdgeCaseHandler:
    """Handle all edge cases in log analysis."""
    
    def __init__(self):
        self.supported_encodings = ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1', 'cp1252', 'iso-8859-1']
        self.max_log_size_mb = 500
        self.min_valid_entries = 10
        self.max_repair_attempts = 3
        
        # Common log timestamp patterns for flexible extraction
        self.timestamp_patterns = [
            # Mailbird format: 2025-06-25 10:15:32.1234
            re.compile(r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.\d{1,4})"),
            # ISO format: 2025-06-25T10:15:32.123Z
            re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z?)"),
            # Common formats: 25/06/2025 10:15:32
            re.compile(r"^(\d{1,2}/\d{1,2}/\d{4}\s\d{2}:\d{2}:\d{2})"),
            # US format: 06/25/2025 10:15:32
            re.compile(r"^(\d{1,2}/\d{1,2}/\d{4}\s\d{2}:\d{2}:\d{2})"),
            # Syslog format: Jun 25 10:15:32
            re.compile(r"^([A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"),
            # Apache format: [25/Jun/2025:10:15:32 +0000]
            re.compile(r"^\[(\d{2}/[A-Za-z]{3}/\d{4}:\d{2}:\d{2}:\d{2}\s[+-]\d{4})\]"),
        ]
        
        # Multi-language error pattern mappings
        self.multi_language_patterns = {
            'connection_errors': {
                'en': [r"connection.*failed", r"unable.*connect", r"timeout.*connect", r"network.*unreachable"],
                'es': [r"conexión.*fallida", r"no.*puede.*conectar", r"tiempo.*agotado", r"red.*inalcanzable"],
                'de': [r"verbindung.*fehlgeschlagen", r"kann.*nicht.*verbinden", r"zeitüberschreitung", r"netzwerk.*nicht.*erreichbar"],
                'fr': [r"connexion.*échouée", r"impossible.*connecter", r"délai.*dépassé", r"réseau.*inaccessible"],
                'pt': [r"conexão.*falhou", r"não.*consegue.*conectar", r"tempo.*esgotado", r"rede.*inacessível"],
                'it': [r"connessione.*fallita", r"impossibile.*connettere", r"timeout.*connessione", r"rete.*irraggiungibile"],
                'zh': [r"连接.*失败", r"无法.*连接", r"连接.*超时", r"网络.*不可达"],
                'ja': [r"接続.*失敗", r"接続.*できません", r"接続.*タイムアウト", r"ネットワーク.*到達不可"],
                'ko': [r"연결.*실패", r"연결.*할.*수.*없음", r"연결.*시간.*초과", r"네트워크.*도달.*불가"],
                'ru': [r"соединение.*не.*удалось", r"невозможно.*подключиться", r"тайм-аут.*соединения", r"сеть.*недоступна"]
            },
            'authentication_errors': {
                'en': [r"auth.*failed", r"authentication.*error", r"login.*failed", r"invalid.*credentials"],
                'es': [r"autenticación.*falló", r"error.*autenticación", r"inicio.*sesión.*falló", r"credenciales.*inválidas"],
                'de': [r"authentifizierung.*fehlgeschlagen", r"anmeldung.*fehler", r"ungültige.*anmeldedaten"],
                'fr': [r"authentification.*échouée", r"erreur.*authentification", r"connexion.*échouée", r"identifiants.*invalides"],
                'pt': [r"autenticação.*falhou", r"erro.*autenticação", r"login.*falhou", r"credenciais.*inválidas"],
                'it': [r"autenticazione.*fallita", r"errore.*autenticazione", r"accesso.*fallito", r"credenziali.*non.*valide"],
                'zh': [r"认证.*失败", r"验证.*错误", r"登录.*失败", r"凭据.*无效"],
                'ja': [r"認証.*失敗", r"認証.*エラー", r"ログイン.*失敗", r"資格情報.*無効"],
                'ko': [r"인증.*실패", r"인증.*오류", r"로그인.*실패", r"자격.*증명.*유효하지.*않음"],
                'ru': [r"аутентификация.*не.*удалась", r"ошибка.*аутентификации", r"вход.*не.*удался", r"неверные.*учетные.*данные"]
            }
        }
        
        # Platform-specific error patterns
        self.platform_patterns = {
            'windows': {
                'registry_errors': [
                    re.compile(r"registry.*key.*not.*found", re.IGNORECASE),
                    re.compile(r"access.*denied.*registry", re.IGNORECASE),
                    re.compile(r"HKEY_.*error", re.IGNORECASE)
                ],
                'permission_errors': [
                    re.compile(r"access.*denied", re.IGNORECASE),
                    re.compile(r"insufficient.*privileges", re.IGNORECASE),
                    re.compile(r"elevated.*permissions.*required", re.IGNORECASE)
                ]
            },
            'macos': {
                'keychain_errors': [
                    re.compile(r"keychain.*access.*denied", re.IGNORECASE),
                    re.compile(r"errSecAuthFailed", re.IGNORECASE),
                    re.compile(r"security.*framework.*error", re.IGNORECASE)
                ],
                'sandbox_errors': [
                    re.compile(r"sandbox.*violation", re.IGNORECASE),
                    re.compile(r"operation.*not.*permitted", re.IGNORECASE),
                    re.compile(r"code.*signing.*error", re.IGNORECASE)
                ]
            },
            'linux': {
                'permission_errors': [
                    re.compile(r"permission.*denied", re.IGNORECASE),
                    re.compile(r"operation.*not.*permitted", re.IGNORECASE),
                    re.compile(r"access.*forbidden", re.IGNORECASE)
                ],
                'dbus_errors': [
                    re.compile(r"dbus.*error", re.IGNORECASE),
                    re.compile(r"failed.*to.*connect.*dbus", re.IGNORECASE)
                ]
            }
        }
    
    async def preprocess_log_content(self, raw_content: Any) -> str:
        """
        Handle various input formats and edge cases.
        """
        try:
            logger.info("Starting log content preprocessing")
            
            # Handle None or empty input
            if not raw_content:
                logger.warning("Empty or None log content provided")
                return ""
            
            # Convert bytes to string if needed
            if isinstance(raw_content, bytes):
                raw_content = await self._decode_bytes_content(raw_content)
            
            # Handle string input
            if isinstance(raw_content, str):
                # Check for compressed content
                if self._is_compressed_string(raw_content):
                    raw_content = await self._decompress_string_content(raw_content)
                
                # Check for base64 encoded content
                if self._is_base64_encoded(raw_content):
                    raw_content = await self._decode_base64_content(raw_content)
                
                # Handle JSON-wrapped content
                if self._is_json_wrapped(raw_content):
                    raw_content = await self._extract_from_json(raw_content)
            
            # Handle list of log entries
            elif isinstance(raw_content, list):
                raw_content = '\n'.join(str(entry) for entry in raw_content)
            
            # Handle dictionary (structured log data)
            elif isinstance(raw_content, dict):
                raw_content = await self._extract_from_dict(raw_content)
            
            # Validate and repair log structure
            raw_content = await self._repair_log_structure(raw_content)
            
            # Remove or handle problematic characters
            raw_content = await self._sanitize_content(raw_content)
            
            logger.info(f"Preprocessing completed, final content length: {len(raw_content)} characters")
            return raw_content
            
        except Exception as e:
            logger.error(f"Preprocessing failed: {str(e)}")
            # Return original content as fallback
            return str(raw_content) if raw_content else ""
    
    async def _decode_bytes_content(self, content: bytes) -> str:
        """Decode bytes content with encoding detection."""
        try:
            # Try to detect encoding
            detected = chardet.detect(content)
            encoding = detected.get('encoding', 'utf-8')
            confidence = detected.get('confidence', 0.0)
            
            logger.info(f"Detected encoding: {encoding} (confidence: {confidence:.2f})")
            
            # If confidence is low, try common encodings
            if confidence < 0.7:
                for enc in self.supported_encodings:
                    try:
                        decoded = content.decode(enc, errors='strict')
                        logger.info(f"Successfully decoded with {enc}")
                        return decoded
                    except UnicodeDecodeError:
                        continue
            
            # Use detected encoding with error handling
            try:
                return content.decode(encoding, errors='replace')
            except:
                return content.decode('utf-8', errors='replace')
                
        except Exception as e:
            logger.error(f"Encoding detection failed: {str(e)}")
            return content.decode('utf-8', errors='replace')
    
    def _is_compressed_string(self, content: str) -> bool:
        """Check if string content appears to be compressed."""
        try:
            # Check for gzip header in base64 encoded content
            if content.startswith('H4sI') or content.startswith('1f8b'):
                return True
            
            # Check for other compression indicators
            compression_indicators = ['eJy', 'eNp', 'eNo']  # Common zlib/deflate prefixes
            return any(content.startswith(indicator) for indicator in compression_indicators)
        except:
            return False
    
    async def _decompress_string_content(self, content: str) -> str:
        """Decompress string content."""
        try:
            # Try base64 decode first
            try:
                decoded_bytes = base64.b64decode(content)
            except:
                decoded_bytes = content.encode('utf-8')
            
            # Try different decompression methods
            decompression_methods = [
                lambda x: zlib.decompress(x, 16 + zlib.MAX_WBITS),  # gzip
                lambda x: zlib.decompress(x, -zlib.MAX_WBITS),      # raw deflate
                lambda x: zlib.decompress(x)                         # zlib
            ]
            
            for method in decompression_methods:
                try:
                    decompressed = method(decoded_bytes)
                    return decompressed.decode('utf-8', errors='replace')
                except:
                    continue
            
            logger.warning("Could not decompress content, returning original")
            return content
            
        except Exception as e:
            logger.error(f"Decompression failed: {str(e)}")
            return content
    
    def _is_base64_encoded(self, content: str) -> bool:
        """Check if content is base64 encoded."""
        try:
            # Basic checks
            if len(content) % 4 != 0:
                return False
            
            # Check for valid base64 characters
            base64_pattern = re.compile(r'^[A-Za-z0-9+/]*={0,2}$')
            if not base64_pattern.match(content):
                return False
            
            # Try to decode
            base64.b64decode(content, validate=True)
            
            # Additional heuristic: base64 encoded text usually doesn't have spaces
            # and is longer than typical log content
            if len(content) > 100 and ' ' not in content and '\n' not in content:
                return True
            
            return False
        except:
            return False
    
    async def _decode_base64_content(self, content: str) -> str:
        """Decode base64 content."""
        try:
            decoded_bytes = base64.b64decode(content)
            return decoded_bytes.decode('utf-8', errors='replace')
        except Exception as e:
            logger.error(f"Base64 decoding failed: {str(e)}")
            return content
    
    def _is_json_wrapped(self, content: str) -> bool:
        """Check if content is wrapped in JSON."""
        try:
            content = content.strip()
            if content.startswith('{') and content.endswith('}'):
                json.loads(content)
                return True
            return False
        except:
            return False
    
    async def _extract_from_json(self, content: str) -> str:
        """Extract log content from JSON wrapper."""
        try:
            data = json.loads(content)
            
            # Common JSON log formats
            possible_keys = ['logs', 'log_content', 'content', 'data', 'entries', 'messages']
            
            for key in possible_keys:
                if key in data:
                    value = data[key]
                    if isinstance(value, str):
                        return value
                    elif isinstance(value, list):
                        return '\n'.join(str(item) for item in value)
            
            # If no specific key found, return string representation
            return str(data)
            
        except Exception as e:
            logger.error(f"JSON extraction failed: {str(e)}")
            return content
    
    async def _extract_from_dict(self, content: dict) -> str:
        """Extract log content from dictionary structure."""
        try:
            # Handle structured logging formats
            if 'entries' in content and isinstance(content['entries'], list):
                entries = []
                for entry in content['entries']:
                    if isinstance(entry, dict):
                        # Try to reconstruct log line
                        timestamp = entry.get('timestamp', '')
                        level = entry.get('level', '')
                        message = entry.get('message', str(entry))
                        entries.append(f"{timestamp}|{level}|{message}")
                    else:
                        entries.append(str(entry))
                return '\n'.join(entries)
            
            # Handle simple key-value logs
            elif 'log' in content or 'logs' in content:
                log_data = content.get('log', content.get('logs', ''))
                return str(log_data)
            
            # Convert entire dict to string representation
            else:
                return json.dumps(content, indent=2)
                
        except Exception as e:
            logger.error(f"Dictionary extraction failed: {str(e)}")
            return str(content)
    
    async def _repair_log_structure(self, content: str) -> str:
        """Repair common log structure issues."""
        try:
            if not content or not content.strip():
                return content
            
            lines = content.split('\n')
            repaired_lines = []
            previous_timestamp = None
            
            for i, line in enumerate(lines):
                # Skip empty lines
                if not line.strip():
                    continue
                
                # Handle lines that are too long (potential corruption)
                if len(line) > 10000:
                    logger.warning(f"Truncating excessively long line at position {i}")
                    line = line[:10000] + "... [TRUNCATED]"
                
                # Try to repair malformed timestamps
                if self._has_malformed_timestamp(line):
                    repaired_line = await self._repair_timestamp(line, previous_timestamp)
                    if repaired_line != line:
                        logger.debug(f"Repaired timestamp in line {i}")
                        line = repaired_line
                
                # Extract and store timestamp for reference
                timestamp = await self._extract_timestamp_flexible(line)
                if timestamp:
                    previous_timestamp = timestamp
                
                # Handle continuation lines (lines that don't start with timestamp)
                if (i > 0 and not await self._extract_timestamp_flexible(line) and 
                    repaired_lines and not line.startswith(' ') and not line.startswith('\t')):
                    # This might be a continuation of the previous line
                    if len(repaired_lines[-1]) < 5000:  # Avoid creating monster lines
                        repaired_lines[-1] += " " + line.strip()
                        continue
                
                repaired_lines.append(line)
            
            # Final validation and cleanup
            repaired_content = '\n'.join(repaired_lines)
            
            # Remove common encoding artifacts
            repaired_content = repaired_content.replace('\ufeff', '')  # BOM
            repaired_content = repaired_content.replace('\x00', '')    # Null bytes
            
            return repaired_content
            
        except Exception as e:
            logger.error(f"Log structure repair failed: {str(e)}")
            return content
    
    def _has_malformed_timestamp(self, line: str) -> bool:
        """Check if line has a malformed timestamp."""
        if not line.strip():
            return False
        
        # Check for partial timestamps or common corruption patterns
        malformed_patterns = [
            r'^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}$',  # Missing seconds
            r'^\d{4}-\d{2}-\d{2}$',               # Missing time
            r'^\d{2}:\d{2}:\d{2}\.',              # Missing date
            r'^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.$',  # Truncated milliseconds
        ]
        
        for pattern in malformed_patterns:
            if re.match(pattern, line):
                return True
        
        return False
    
    async def _repair_timestamp(self, line: str, reference_timestamp: Optional[datetime]) -> str:
        """Attempt to repair malformed timestamps."""
        try:
            # If we have a reference timestamp, use it to fill in missing parts
            if reference_timestamp:
                # Try to match partial patterns and complete them
                if re.match(r'^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}$', line):
                    # Missing seconds, add :00
                    line = line + ":00.0000"
                elif re.match(r'^\d{4}-\d{2}-\d{2}$', line):
                    # Missing time, use reference time
                    time_part = reference_timestamp.strftime("%H:%M:%S.%f")[:-2]
                    line = line + " " + time_part
                elif re.match(r'^\d{2}:\d{2}:\d{2}\.', line):
                    # Missing date, use reference date
                    date_part = reference_timestamp.strftime("%Y-%m-%d")
                    line = date_part + " " + line
            
            return line
            
        except Exception as e:
            logger.error(f"Timestamp repair failed: {str(e)}")
            return line
    
    async def _extract_timestamp_flexible(self, line: str) -> Optional[datetime]:
        """Extract timestamp using multiple flexible patterns."""
        for pattern in self.timestamp_patterns:
            match = pattern.search(line)
            if match:
                timestamp_str = match.group(1)
                
                # Try to parse with different formats
                formats = [
                    "%Y-%m-%d %H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%SZ",
                    "%Y-%m-%dT%H:%M:%S",
                    "%d/%m/%Y %H:%M:%S",
                    "%m/%d/%Y %H:%M:%S",
                    "%Y/%m/%d %H:%M:%S",
                ]
                
                for fmt in formats:
                    try:
                        return datetime.strptime(timestamp_str, fmt)
                    except ValueError:
                        continue
        
        return None
    
    async def _sanitize_content(self, content: str) -> str:
        """Remove or handle problematic characters and content."""
        try:
            # Remove control characters (except newlines and tabs)
            content = ''.join(char for char in content if ord(char) >= 32 or char in '\n\t\r')
            
            # Handle excessively long lines that might cause issues
            lines = content.split('\n')
            sanitized_lines = []
            
            for line in lines:
                if len(line) > 20000:  # Very long line, might be corrupted
                    # Try to find logical break points
                    if '|' in line:
                        # Split on pipe separators (common in Mailbird logs)
                        parts = line.split('|')
                        current_line = parts[0]
                        for part in parts[1:]:
                            if len(current_line + '|' + part) > 5000:
                                sanitized_lines.append(current_line)
                                current_line = part
                            else:
                                current_line += '|' + part
                        if current_line:
                            sanitized_lines.append(current_line)
                    else:
                        # Just truncate with indication
                        sanitized_lines.append(line[:5000] + "... [LINE_TRUNCATED]")
                else:
                    sanitized_lines.append(line)
            
            return '\n'.join(sanitized_lines)
            
        except Exception as e:
            logger.error(f"Content sanitization failed: {str(e)}")
            return content
    
    def validate_analysis_input(self, log_content: str) -> Dict[str, Any]:
        """Validate log content before analysis."""
        validation_result = {
            'is_valid': True,
            'issues': [],
            'warnings': [],
            'suggestions': [],
            'metrics': {},
            'detected_language': 'en',
            'detected_platform': 'unknown'
        }
        
        try:
            # Basic metrics
            size_mb = len(log_content.encode('utf-8')) / (1024 * 1024)
            line_count = log_content.count('\n')
            char_count = len(log_content)
            
            validation_result['metrics'] = {
                'size_mb': round(size_mb, 2),
                'line_count': line_count,
                'char_count': char_count,
                'average_line_length': round(char_count / max(line_count, 1), 2) if line_count > 0 else 0
            }
            
            # Size validation
            if size_mb > self.max_log_size_mb:
                validation_result['issues'].append(
                    f"Log size ({size_mb:.1f}MB) exceeds recommended limit ({self.max_log_size_mb}MB)"
                )
                validation_result['suggestions'].append(
                    "Consider splitting the log file or using time-based filtering"
                )
            elif size_mb > self.max_log_size_mb * 0.8:
                validation_result['warnings'].append(
                    f"Log size ({size_mb:.1f}MB) is approaching the limit"
                )
            
            # Entry count validation
            if line_count < self.min_valid_entries:
                validation_result['issues'].append(
                    f"Too few log entries ({line_count}), minimum required: {self.min_valid_entries}"
                )
                validation_result['suggestions'].append(
                    "Ensure complete log file is provided with sufficient entries"
                )
            
            # Content quality checks
            if not log_content.strip():
                validation_result['issues'].append("Log content is empty")
                validation_result['is_valid'] = False
                return validation_result
            
            # Check for encoding issues
            if '�' in log_content:
                validation_result['warnings'].append("Encoding issues detected (replacement characters found)")
                validation_result['suggestions'].append("Re-export log with UTF-8 encoding if possible")
            
            # Check for truncation indicators
            truncation_indicators = ['[TRUNCATED]', '[LINE_TRUNCATED]', '...truncated']
            if any(indicator in log_content for indicator in truncation_indicators):
                validation_result['warnings'].append("Truncated content detected")
                validation_result['suggestions'].append("Provide complete log file for better analysis")
            
            # Detect language
            validation_result['detected_language'] = self._detect_content_language(log_content)
            
            # Detect platform
            validation_result['detected_platform'] = self._detect_platform(log_content)
            
            # Check timestamp consistency
            timestamp_issues = self._check_timestamp_consistency(log_content)
            if timestamp_issues:
                validation_result['warnings'].extend(timestamp_issues)
            
            # Final validation
            validation_result['is_valid'] = len(validation_result['issues']) == 0
            
            logger.info(f"Validation completed: {'PASSED' if validation_result['is_valid'] else 'FAILED'}")
            
        except Exception as e:
            logger.error(f"Validation failed: {str(e)}")
            validation_result['issues'].append(f"Validation error: {str(e)}")
            validation_result['is_valid'] = False
        
        return validation_result
    
    def _detect_content_language(self, content: str) -> str:
        """Detect the primary language of log content."""
        try:
            # Sample first 5000 characters for language detection
            sample = content[:5000].lower()
            
            language_scores = {}
            
            for lang_code, patterns_dict in self.multi_language_patterns.items():
                for lang, patterns in patterns_dict.items():
                    if lang not in language_scores:
                        language_scores[lang] = 0
                    
                    for pattern in patterns:
                        matches = len(re.findall(pattern, sample, re.IGNORECASE))
                        language_scores[lang] += matches
            
            # Return language with highest score, default to English
            if language_scores:
                detected_lang = max(language_scores, key=language_scores.get)
                if language_scores[detected_lang] > 0:
                    return detected_lang
            
            return 'en'  # Default to English
            
        except Exception as e:
            logger.error(f"Language detection failed: {str(e)}")
            return 'en'
    
    def _detect_platform(self, content: str) -> str:
        """Detect the platform (Windows, macOS, Linux) from log content."""
        try:
            content_lower = content.lower()
            
            platform_indicators = {
                'windows': [
                    'registry', 'hkey_', 'c:\\', 'windows', 'ntdll', 'kernel32',
                    'access denied', 'insufficient privileges', '.exe', 'powershell'
                ],
                'macos': [
                    'keychain', 'sandbox', 'corefoundation', 'cocoa', '/users/',
                    'launchd', 'errsecsuccess', 'operation not permitted', 'darwin'
                ],
                'linux': [
                    '/home/', '/usr/', '/var/', 'dbus', 'systemd', 'glibc',
                    'permission denied', '/proc/', '.so', 'bash'
                ]
            }
            
            platform_scores = {}
            
            for platform, indicators in platform_indicators.items():
                score = sum(content_lower.count(indicator) for indicator in indicators)
                platform_scores[platform] = score
            
            # Return platform with highest score
            if platform_scores:
                detected_platform = max(platform_scores, key=platform_scores.get)
                if platform_scores[detected_platform] > 0:
                    return detected_platform
            
            return 'unknown'
            
        except Exception as e:
            logger.error(f"Platform detection failed: {str(e)}")
            return 'unknown'
    
    def _check_timestamp_consistency(self, content: str) -> List[str]:
        """Check for timestamp consistency issues."""
        issues = []
        
        try:
            lines = content.split('\n')[:100]  # Check first 100 lines
            timestamps = []
            
            for line in lines:
                if line.strip():
                    timestamp = asyncio.run(self._extract_timestamp_flexible(line))
                    if timestamp:
                        timestamps.append(timestamp)
            
            if len(timestamps) < 2:
                return issues
            
            # Check for time ordering issues
            out_of_order_count = 0
            for i in range(1, len(timestamps)):
                if timestamps[i] < timestamps[i-1]:
                    out_of_order_count += 1
            
            if out_of_order_count > len(timestamps) * 0.1:  # More than 10% out of order
                issues.append("Timestamps appear to be out of chronological order")
            
            # Check for large time gaps
            time_gaps = []
            for i in range(1, len(timestamps)):
                gap = (timestamps[i] - timestamps[i-1]).total_seconds()
                time_gaps.append(abs(gap))
            
            if time_gaps:
                avg_gap = sum(time_gaps) / len(time_gaps)
                max_gap = max(time_gaps)
                
                if max_gap > avg_gap * 100:  # Unusually large gap
                    issues.append("Unusually large time gaps detected between log entries")
            
        except Exception as e:
            logger.error(f"Timestamp consistency check failed: {str(e)}")
        
        return issues
    
    def handle_multi_file_logs(self, log_files: List[str]) -> str:
        """Merge multiple log files maintaining chronological order."""
        try:
            logger.info(f"Merging {len(log_files)} log files")
            
            all_entries = []
            
            for i, file_content in enumerate(log_files):
                try:
                    # Preprocess each file
                    processed = asyncio.run(self.preprocess_log_content(file_content))
                    entries = self._parse_to_entries(processed, file_index=i)
                    all_entries.extend(entries)
                    logger.debug(f"Processed file {i+1}: {len(entries)} entries")
                except Exception as e:
                    logger.error(f"Failed to process file {i+1}: {str(e)}")
                    continue
            
            if not all_entries:
                logger.error("No valid entries found in any file")
                return ""
            
            # Sort by timestamp
            all_entries.sort(key=lambda x: x.get('timestamp') or datetime.min)
            
            # Reconstruct log content
            merged_content = self._entries_to_log_content(all_entries)
            
            logger.info(f"Successfully merged {len(all_entries)} entries from {len(log_files)} files")
            return merged_content
            
        except Exception as e:
            logger.error(f"Multi-file merge failed: {str(e)}")
            # Return concatenated content as fallback
            return '\n'.join(str(content) for content in log_files)
    
    def _parse_to_entries(self, content: str, file_index: int = 0) -> List[Dict]:
        """Parse log content to structured entries."""
        entries = []
        
        try:
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines):
                if not line.strip():
                    continue
                
                entry = {
                    'original_line': line,
                    'line_number': line_num + 1,
                    'file_index': file_index,
                    'timestamp': None
                }
                
                # Extract timestamp
                timestamp = asyncio.run(self._extract_timestamp_flexible(line))
                if timestamp:
                    entry['timestamp'] = timestamp
                else:
                    entry['timestamp'] = datetime.min  # For sorting purposes
                
                entries.append(entry)
                
        except Exception as e:
            logger.error(f"Entry parsing failed: {str(e)}")
        
        return entries
    
    def _entries_to_log_content(self, entries: List[Dict]) -> str:
        """Convert structured entries back to log content."""
        try:
            lines = []
            for entry in entries:
                line = entry.get('original_line', '')
                if line.strip():
                    lines.append(line)
            
            return '\n'.join(lines)
            
        except Exception as e:
            logger.error(f"Entry reconstruction failed: {str(e)}")
            return ""
    
    def get_platform_specific_patterns(self, platform: str) -> Dict[str, List]:
        """Get platform-specific error patterns."""
        return self.platform_patterns.get(platform.lower(), {})
    
    def get_language_patterns(self, language: str) -> Dict[str, List[str]]:
        """Get language-specific error patterns."""
        patterns = {}
        for category, lang_patterns in self.multi_language_patterns.items():
            patterns[category] = lang_patterns.get(language, lang_patterns.get('en', []))
        return patterns