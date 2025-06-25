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
import asyncio
import logging
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import DBSCAN
import numpy as np
from .edge_case_handler import EdgeCaseHandler

logger = logging.getLogger(__name__)

class AdvancedMailbirdAnalyzer:
    """
    Advanced log analyzer that provides account-specific analysis, temporal patterns,
    and detailed issue categorization matching the quality of sample reports.
    """
    
    def __init__(self):
        self.accounts = {}  # Track per-account issues
        self.temporal_patterns = []  # Track time-based patterns
        self.issue_correlations = {}  # Track related issues
        
        # Initialize edge case handler for preprocessing
        self.edge_case_handler = EdgeCaseHandler()
        
        # Dynamic pattern learning
        self.learned_patterns = {}
        self.pattern_confidence_threshold = 0.85
        
        # Cross-platform patterns
        self.platform_specific_patterns = {
            'windows': {
                'registry_access_failure': {
                    'patterns': [
                        re.compile(r"registry.*key.*not.*found.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                        re.compile(r"access.*denied.*registry.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                        re.compile(r"HKEY_.*error.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    ],
                    'severity': 'high',
                    'category': 'Windows Registry Access Issues',
                    'impact': 'Unable to store or retrieve account settings from Windows Registry'
                },
                'com_activation_failure': {
                    'patterns': [
                        re.compile(r"COM.*activation.*failed.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                        re.compile(r"CLSID.*not.*registered.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    ],
                    'severity': 'medium',
                    'category': 'Windows COM Component Issues',
                    'impact': 'Features requiring COM components may not function properly'
                }
            },
            'macos': {
                'keychain_access_failure': {
                    'patterns': [
                        re.compile(r"Keychain.*access.*denied.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                        re.compile(r"errSecAuthFailed.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                        re.compile(r"security.*framework.*error.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    ],
                    'severity': 'high',
                    'category': 'macOS Keychain Authentication Issues',
                    'impact': 'Unable to retrieve stored passwords from macOS Keychain'
                },
                'sandbox_violation': {
                    'patterns': [
                        re.compile(r"sandbox.*violation.*mailbird.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                        re.compile(r"operation.*not.*permitted.*mail.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                        re.compile(r"code.*signing.*error.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    ],
                    'severity': 'critical',
                    'category': 'macOS Sandbox Restrictions',
                    'impact': 'Limited file system access affecting attachments and data storage'
                }
            },
            'linux': {
                'dbus_connection_failure': {
                    'patterns': [
                        re.compile(r"dbus.*connection.*failed.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                        re.compile(r"failed.*to.*connect.*dbus.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    ],
                    'severity': 'medium',
                    'category': 'Linux D-Bus Communication Issues',
                    'impact': 'Desktop integration features may not work properly'
                },
                'permission_denied': {
                    'patterns': [
                        re.compile(r"permission.*denied.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                        re.compile(r"operation.*not.*permitted.*([^@\s]+@[^@\s]+)", re.IGNORECASE),
                    ],
                    'severity': 'high',
                    'category': 'Linux Permission Issues',
                    'impact': 'Unable to access required files or directories'
                }
            }
        }
        
        # Multi-language support
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
            },
            'email_send_errors': {
                'en': [r"send.*failed", r"message.*not.*sent", r"delivery.*failed", r"smtp.*error"],
                'es': [r"envío.*falló", r"mensaje.*no.*enviado", r"entrega.*falló", r"error.*smtp"],
                'de': [r"senden.*fehlgeschlagen", r"nachricht.*nicht.*gesendet", r"zustellung.*fehler", r"smtp.*fehler"],
                'fr': [r"envoi.*échoué", r"message.*non.*envoyé", r"livraison.*échouée", r"erreur.*smtp"],
                'pt': [r"envio.*falhou", r"mensagem.*não.*enviada", r"entrega.*falhou", r"erro.*smtp"],
                'it': [r"invio.*fallito", r"messaggio.*non.*inviato", r"consegna.*fallita", r"errore.*smtp"],
                'zh': [r"发送.*失败", r"消息.*未.*发送", r"投递.*失败", r"smtp.*错误"],
                'ja': [r"送信.*失敗", r"メッセージ.*送信.*されませんでした", r"配信.*失敗", r"smtp.*エラー"],
                'ko': [r"전송.*실패", r"메시지.*전송.*안됨", r"배달.*실패", r"smtp.*오류"],
                'ru': [r"отправка.*не.*удалась", r"сообщение.*не.*отправлено", r"доставка.*не.*удалась", r"ошибка.*smtp"]
            }
        }
        
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

    async def analyze_logs(self, raw_log_content: str, platform: str = 'unknown', language: str = 'en') -> Dict[str, Any]:
        """
        Perform comprehensive log analysis with account-specific tracking and temporal patterns.
        Enhanced with cross-platform support, ML pattern discovery, and multi-language support.
        """
        # Preprocess log content using edge case handler
        try:
            processed_content = await self.edge_case_handler.preprocess_log_content(raw_log_content)
            validation_result = self.edge_case_handler.validate_analysis_input(processed_content)
            
            if not validation_result['is_valid']:
                logger.warning(f"Log validation issues: {validation_result['issues']}")
            
            # Use detected platform and language if not specified
            if platform == 'unknown':
                platform = validation_result.get('detected_platform', 'unknown')
            if language == 'en':
                language = validation_result.get('detected_language', 'en')
                
        except Exception as e:
            logger.error(f"Log preprocessing failed: {str(e)}")
            processed_content = raw_log_content
            validation_result = {'is_valid': True, 'warnings': []}
        
        lines = processed_content.strip().split('\n')
        
        # Parse each line and extract detailed information
        parsed_entries = []
        account_issues = defaultdict(list)
        temporal_events = []
        positive_observations = []
        
        for line_num, line in enumerate(lines, 1):
            entry = await self._parse_log_line(line, line_num, platform, language)
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
        
        # Perform ML-based pattern discovery on unmatched entries
        unmatched_entries = [entry for entry in parsed_entries if not entry.get('issue_type')]
        if len(unmatched_entries) > 10:  # Only run ML if we have enough data
            try:
                ml_discovered_patterns = await self.discover_patterns_with_ml(unmatched_entries)
                logger.info(f"ML discovered {len(ml_discovered_patterns)} new patterns")
            except Exception as e:
                logger.error(f"ML pattern discovery failed: {str(e)}")
                ml_discovered_patterns = []
        else:
            ml_discovered_patterns = []
        
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
            'ml_discovered_patterns': ml_discovered_patterns,
            'platform_specific_issues': self._analyze_platform_specific_issues(parsed_entries, platform),
            'language_analysis': {
                'detected_language': language,
                'multi_language_errors': self._detect_multi_language_errors(parsed_entries, language)
            },
            'validation_results': validation_result,
            'metadata': {
                'total_entries_parsed': len(parsed_entries),
                'unique_accounts': len(account_issues),
                'error_rate_percentage': self._calculate_error_rate(parsed_entries),
                'log_timeframe': self._extract_timeframe(parsed_entries),
                'analysis_timestamp': datetime.utcnow().isoformat(),
                'platform': platform,
                'language': language,
                'preprocessing_applied': processed_content != raw_log_content,
                'ml_patterns_discovered': len(ml_discovered_patterns)
            }
        }

    async def _parse_log_line(self, line: str, line_num: int, platform: str = 'unknown', language: str = 'en') -> Optional[Dict[str, Any]]:
        """Parse individual log line with comprehensive pattern matching including cross-platform and multi-language support."""
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
            'status': 'unknown',
            'platform': platform,
            'language': language
        }
        
        # Extract account information
        entry['account'] = self._extract_account(line)
        
        # First check standard issue patterns
        issue_found = False
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
                        entry['extracted_account'] = entry.get('account')
                    issue_found = True
                    break
            if issue_found:
                break
        
        # Check platform-specific patterns if no standard issue found
        if not issue_found and platform in self.platform_specific_patterns:
            for issue_type, config in self.platform_specific_patterns[platform].items():
                for pattern in config['patterns']:
                    match = pattern.search(line)
                    if match:
                        entry['issue_type'] = f"{platform}_{issue_type}"
                        entry['severity'] = config['severity']
                        entry['category'] = config['category']
                        entry['impact'] = config['impact']
                        entry['status'] = 'error'
                        entry['platform_specific'] = True
                        
                        try:
                            if match.groups() and len(match.groups()) > 0:
                                entry['extracted_account'] = match.group(1)
                        except (IndexError, AttributeError):
                            entry['extracted_account'] = entry.get('account')
                        issue_found = True
                        break
                if issue_found:
                    break
        
        # Check multi-language patterns if no issue found yet
        if not issue_found:
            await self._check_multi_language_patterns(line, entry, language)
        
        # Detect success patterns (multi-language)
        success_keywords = {
            'en': ['success', 'connected', 'authenticated', 'sync complete', 'login successful'],
            'es': ['éxito', 'conectado', 'autenticado', 'sincronización completa'],
            'de': ['erfolg', 'verbunden', 'authentifiziert', 'synchronisation abgeschlossen'],
            'fr': ['succès', 'connecté', 'authentifié', 'synchronisation terminée'],
            'pt': ['sucesso', 'conectado', 'autenticado', 'sincronização completa'],
            'it': ['successo', 'connesso', 'autenticato', 'sincronizzazione completata'],
            'zh': ['成功', '已连接', '已认证', '同步完成'],
            'ja': ['成功', '接続済み', '認証済み', '同期完了'],
            'ko': ['성공', '연결됨', '인증됨', '동기화 완료'],
            'ru': ['успех', 'подключено', 'аутентифицировано', 'синхронизация завершена']
        }
        
        keywords = success_keywords.get(language, success_keywords['en'])
        if any(keyword in line.lower() for keyword in keywords):
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

    async def discover_patterns_with_ml(self, unmatched_entries: List[Dict]) -> List[Dict]:
        """
        Use machine learning techniques to discover new error patterns.
        Identifies clusters of similar errors that don't match existing patterns.
        """
        try:
            if len(unmatched_entries) < 10:
                return []
            
            # Extract text content for analysis
            texts = [entry['raw_content'] for entry in unmatched_entries]
            
            # Use TF-IDF vectorization
            vectorizer = TfidfVectorizer(
                max_features=1000,
                stop_words='english',
                ngram_range=(1, 3),
                min_df=2,
                max_df=0.8
            )
            
            tfidf_matrix = vectorizer.fit_transform(texts)
            
            # Use DBSCAN clustering to find similar patterns
            clustering = DBSCAN(eps=0.3, min_samples=3, metric='cosine')
            cluster_labels = clustering.fit_predict(tfidf_matrix.toarray())
            
            # Analyze clusters to identify new patterns
            discovered_patterns = []
            unique_labels = set(cluster_labels)
            
            for label in unique_labels:
                if label == -1:  # Noise cluster
                    continue
                
                cluster_entries = [entry for i, entry in enumerate(unmatched_entries) if cluster_labels[i] == label]
                if len(cluster_entries) < 3:
                    continue
                
                # Extract common pattern from cluster
                pattern_analysis = await self._analyze_cluster_pattern(cluster_entries, vectorizer, tfidf_matrix, cluster_labels == label)
                
                if pattern_analysis and pattern_analysis['confidence'] > self.pattern_confidence_threshold:
                    discovered_patterns.append({
                        'pattern_id': f"ml_discovered_{label}",
                        'pattern_regex': pattern_analysis['suggested_regex'],
                        'category': pattern_analysis['category'],
                        'severity': pattern_analysis['severity'],
                        'sample_entries': [entry['raw_content'] for entry in cluster_entries[:3]],
                        'occurrences': len(cluster_entries),
                        'confidence': pattern_analysis['confidence'],
                        'keywords': pattern_analysis['keywords']
                    })
            
            # Store learned patterns for future use
            for pattern in discovered_patterns:
                self.learned_patterns[pattern['pattern_id']] = pattern
            
            logger.info(f"ML discovered {len(discovered_patterns)} new patterns")
            return discovered_patterns
            
        except Exception as e:
            logger.error(f"ML pattern discovery failed: {str(e)}")
            return []

    async def _analyze_cluster_pattern(self, cluster_entries: List[Dict], vectorizer, tfidf_matrix: np.ndarray, cluster_mask: np.ndarray) -> Optional[Dict]:
        """Analyze a cluster of similar entries to extract pattern information."""
        try:
            # Get feature names and TF-IDF scores for the cluster
            feature_names = vectorizer.get_feature_names_out()
            cluster_tfidf = tfidf_matrix[cluster_mask]
            mean_scores = np.mean(cluster_tfidf, axis=0).A1
            
            # Get top keywords for this cluster
            top_indices = np.argsort(mean_scores)[-10:]
            top_keywords = [feature_names[i] for i in top_indices if mean_scores[i] > 0.1]
            
            if len(top_keywords) < 2:
                return None
            
            # Analyze entry content to determine category and severity
            sample_texts = [entry['raw_content'].lower() for entry in cluster_entries]
            
            # Determine category based on keywords
            category = "Unknown Issue"
            severity = "medium"
            
            error_indicators = ['error', 'failed', 'failure', 'exception', 'timeout', 'denied']
            warning_indicators = ['warning', 'warn', 'deprecated', 'slow']
            critical_indicators = ['critical', 'fatal', 'crash', 'abort', 'corruption']
            
            if any(indicator in ' '.join(top_keywords) for indicator in critical_indicators):
                severity = "critical"
                category = "Critical System Issues"
            elif any(indicator in ' '.join(top_keywords) for indicator in error_indicators):
                severity = "high"
                category = "Error Conditions"
            elif any(indicator in ' '.join(top_keywords) for indicator in warning_indicators):
                severity = "medium"
                category = "Warning Conditions"
            
            # Generate suggested regex pattern
            # This is a simplified approach - in production, more sophisticated pattern generation would be used
            common_words = [word for word in top_keywords if len(word) > 3]
            if common_words:
                suggested_regex = r".*" + r".*".join(re.escape(word) for word in common_words[:3]) + r".*"
            else:
                suggested_regex = None
            
            confidence = min(0.95, len(cluster_entries) / 10.0 + len(top_keywords) / 20.0)
            
            return {
                'category': category,
                'severity': severity,
                'keywords': top_keywords,
                'suggested_regex': suggested_regex,
                'confidence': confidence
            }
            
        except Exception as e:
            logger.error(f"Cluster analysis failed: {str(e)}")
            return None

    async def _check_multi_language_patterns(self, line: str, entry: Dict, language: str):
        """Check line against multi-language error patterns."""
        try:
            line_lower = line.lower()
            
            for error_category, lang_patterns in self.multi_language_patterns.items():
                patterns = lang_patterns.get(language, lang_patterns.get('en', []))
                
                for pattern_str in patterns:
                    try:
                        pattern = re.compile(pattern_str, re.IGNORECASE)
                        if pattern.search(line):
                            entry['issue_type'] = f"multi_lang_{error_category}"
                            entry['category'] = f"Multi-Language {error_category.replace('_', ' ').title()}"
                            entry['severity'] = 'medium'
                            entry['status'] = 'error'
                            entry['language_specific'] = True
                            entry['impact'] = f"Language-specific error in {language}"
                            break
                    except re.error:
                        continue
                
                if entry.get('issue_type'):
                    break
                    
        except Exception as e:
            logger.error(f"Multi-language pattern check failed: {str(e)}")

    def _analyze_platform_specific_issues(self, parsed_entries: List[Dict], platform: str) -> Dict[str, Any]:
        """Analyze platform-specific issues found in the log."""
        platform_issues = [entry for entry in parsed_entries if entry.get('platform_specific', False)]
        
        if not platform_issues:
            return {'platform': platform, 'issues_found': 0, 'recommendations': []}
        
        issue_types = Counter([entry['issue_type'] for entry in platform_issues])
        
        recommendations = []
        if platform == 'windows':
            if any('registry' in issue_type for issue_type in issue_types):
                recommendations.append("Run Mailbird as administrator to resolve registry access issues")
            if any('com' in issue_type for issue_type in issue_types):
                recommendations.append("Re-register COM components or repair Windows installation")
        elif platform == 'macos':
            if any('keychain' in issue_type for issue_type in issue_types):
                recommendations.append("Reset Keychain permissions or create new Keychain entry")
            if any('sandbox' in issue_type for issue_type in issue_types):
                recommendations.append("Check application permissions in System Preferences > Security & Privacy")
        elif platform == 'linux':
            if any('dbus' in issue_type for issue_type in issue_types):
                recommendations.append("Restart D-Bus service or check desktop environment compatibility")
            if any('permission' in issue_type for issue_type in issue_types):
                recommendations.append("Check file permissions and user group memberships")
        
        return {
            'platform': platform,
            'issues_found': len(platform_issues),
            'issue_breakdown': dict(issue_types),
            'recommendations': recommendations,
            'severity_distribution': Counter([entry['severity'] for entry in platform_issues])
        }

    def _detect_multi_language_errors(self, parsed_entries: List[Dict], language: str) -> Dict[str, Any]:
        """Analyze multi-language specific errors."""
        lang_issues = [entry for entry in parsed_entries if entry.get('language_specific', False)]
        
        if not lang_issues:
            return {'language': language, 'issues_found': 0}
        
        issue_categories = Counter([entry['issue_type'].replace('multi_lang_', '') for entry in lang_issues])
        
        return {
            'language': language,
            'issues_found': len(lang_issues),
            'categories': dict(issue_categories),
            'common_patterns': list(issue_categories.most_common(3))
        }

    async def repair_corrupted_log_entries(self, raw_content: str) -> str:
        """
        Attempt to repair corrupted or truncated log entries using:
        - Pattern-based reconstruction
        - Statistical inference from similar entries
        - Partial entry completion
        """
        try:
            lines = raw_content.split('\n')
            repaired_lines = []
            
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                
                # Check if line appears corrupted (e.g., incomplete timestamp, truncated)
                if self._is_corrupted_line(line):
                    repaired_line = await self._attempt_line_repair(line, lines, i)
                    repaired_lines.append(repaired_line)
                else:
                    repaired_lines.append(line)
            
            return '\n'.join(repaired_lines)
            
        except Exception as e:
            logger.error(f"Log repair failed: {str(e)}")
            return raw_content

    def _is_corrupted_line(self, line: str) -> bool:
        """Check if a log line appears corrupted."""
        # Check for incomplete timestamps
        if re.match(r'^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}$', line.strip()):
            return True
        
        # Check for truncated lines (no message part)
        if re.match(r'^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.\d+\|[A-Z]+\|\d+\|\d+\|\d+\|$', line):
            return True
        
        # Check for lines with too many consecutive special characters (corruption)
        if re.search(r'[^\w\s]{10,}', line):
            return True
        
        return False

    async def _attempt_line_repair(self, corrupted_line: str, all_lines: List[str], line_index: int) -> str:
        """Attempt to repair a corrupted log line."""
        try:
            # Strategy 1: If timestamp is incomplete, complete it with seconds
            if re.match(r'^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}$', corrupted_line.strip()):
                return corrupted_line + ":00.0000|INFO|0|0|0|[REPAIRED] Incomplete timestamp completed"
            
            # Strategy 2: If message is missing, check next line for continuation
            if corrupted_line.endswith('|') and line_index + 1 < len(all_lines):
                next_line = all_lines[line_index + 1].strip()
                if not re.match(r'^\d{4}-\d{2}-\d{2}', next_line):  # Next line doesn't start with timestamp
                    return corrupted_line + f"[REPAIRED] {next_line}"
            
            # Strategy 3: Remove excessive special characters
            if re.search(r'[^\w\s]{10,}', corrupted_line):
                cleaned = re.sub(r'[^\w\s|:.-]{3,}', '[CORRUPTED_DATA_REMOVED]', corrupted_line)
                return cleaned
            
            # If no specific repair strategy works, mark as corrupted but keep
            return corrupted_line + " [CORRUPTED_ENTRY]"
            
        except Exception as e:
            logger.error(f"Line repair failed: {str(e)}")
            return corrupted_line


async def enhanced_parse_log_content(raw_log_content: str, platform: str = 'unknown', language: str = 'en') -> Dict[str, Any]:
    """
    Main entry point for enhanced log parsing with comprehensive analysis.
    Enhanced with cross-platform support, ML pattern discovery, and multi-language support.
    """
    analyzer = AdvancedMailbirdAnalyzer()
    return await analyzer.analyze_logs(raw_log_content, platform, language)