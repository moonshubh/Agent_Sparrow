"""Conversational v10 formatter for log analysis results.

Generates empathetic markdown paired with a structured JSON envelope that the
frontend can render into overview cards, findings, quick actions, and more.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import re

from ..schemas.log_schemas import (
    ErrorCategory,
    ErrorPattern,
    IssueImpact,
    LogAnalysisEnvelope,
    LogAnalysisResult,
    LogMetadata,
    RootCause,
    StructuredConfidence,
    FindingSeverity,
    FindingPayload,
    SignatureInfo,
    EvidenceReference,
    QuickActionPayload,
    FixStepPayload,
    OverviewPayload,
    MetaPayload,
    CoveragePayload,
)

from ..privacy.sanitizer import LogSanitizer
from enum import Enum


class SensitiveDataMasker:
    """Applies spec-compliant masking to markdown and structured payloads."""

    EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    TOKEN_RE = re.compile(r"\b[A-Za-z0-9]{24,}\b")
    DOMAIN_RE = re.compile(r"\b(?:(?:[a-z0-9-]+\.)+[a-z]{2,})\b", re.IGNORECASE)
    WINDOWS_PATH_RE = re.compile(r"([A-Z]:\\Users\\)([^\\\s]+)", re.IGNORECASE)
    POSIX_PATH_RE = re.compile(r"(/home/|/users/)([^/\s]+)", re.IGNORECASE)

    def __init__(self, sanitizer: Optional[LogSanitizer] = None):
        self._sanitizer = sanitizer or LogSanitizer()

    def sanitize_text(self, text: str) -> str:
        if not text:
            return text

        sanitized = self._sanitizer.sanitize_for_display(text)
        sanitized = self._standardize_tokens(sanitized)
        sanitized = self._mask_domains_and_paths(sanitized)
        return sanitized

    def sanitize_structure(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            return {key: self.sanitize_structure(value) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self.sanitize_structure(item) for item in payload]
        if isinstance(payload, Enum):
            return payload.value
        if isinstance(payload, str):
            return self.sanitize_text(payload)
        return payload

    def _standardize_tokens(self, text: str) -> str:
        def _mask_email(m: re.Match[str]) -> str:
            raw = m.group(0)
            try:
                name, domain = raw.split("@", 1)
            except ValueError:
                return "***@***"
            masked_name = (name[0] + "***") if name else "***"
            return f"{masked_name}@{domain}"

        # Preserve hashed redaction tags from sanitizer for correlation.
        # Only mask raw patterns that slipped through.
        text = self.EMAIL_RE.sub(_mask_email, text)
        text = self.IP_RE.sub("***.***.***.***", text)
        text = self.TOKEN_RE.sub("[SECRET]", text)
        return text

    def _mask_domains_and_paths(self, text: str) -> str:
        def _mask_domain(match: re.Match[str]) -> str:
            domain = match.group(0)
            if domain.lower() in {"localhost", "127.0.0.1"}:
                return domain
            parts = domain.split('.')
            if len(parts) >= 2:
                return f"***.{'.'.join(parts[-2:])}"
            return "***." + domain

        text = self.DOMAIN_RE.sub(_mask_domain, text)
        text = self.WINDOWS_PATH_RE.sub(r"\1[user]", text)
        text = self.POSIX_PATH_RE.sub(r"\1[user]", text)
        return text


class LogV10Composer:
    """Builds v10 conversational markdown and structured envelope."""

    ENGINE_VERSION = "log-agent-v10.0.0"

    def __init__(self, sanitizer: Optional[LogSanitizer] = None):
        self._masker = SensitiveDataMasker(sanitizer)

    def compose(
        self,
        analysis: LogAnalysisResult,
        *,
        user_query: Optional[str] = None,
        redactions_applied: Optional[Sequence[str]] = None,
        analysis_duration_ms: Optional[int] = None,
    ) -> Tuple[str, LogAnalysisEnvelope, Dict[str, Any]]:
        metadata = analysis.metadata
        files = metadata.source_files or ["uploaded-log.log"]

        findings = self._build_findings(analysis)
        quick_actions = self._derive_quick_actions(analysis)
        fix_steps = self._derive_fix_steps(analysis)
        extra_checks = self._derive_extra_checks(analysis)
        tips = self._derive_tips(analysis)

        confidence_level = self._map_confidence(analysis.confidence_score)
        confidence_reason = self._confidence_reason(confidence_level, analysis, findings)

        overview = OverviewPayload(
            time_range=self._format_time_range(metadata),
            files=files,
            app_version=self._safe_value(metadata.mailbird_version, {"unknown", ""}),
            db_size=self._format_db_size(metadata),
            accounts_count=metadata.account_count or None,
            platform=self._safe_value(metadata.os_version, {"unknown", ""}),
            confidence=confidence_level,
            confidence_reason=self._masker.sanitize_text(confidence_reason),
        )

        envelope = LogAnalysisEnvelope(
            overview=overview,
            findings=findings,
            quick_actions=quick_actions,
            full_fix_steps=fix_steps,
            checks=[self._masker.sanitize_text(item) for item in extra_checks],
            tips=[self._masker.sanitize_text(item) for item in tips],
            redactions_applied=list(redactions_applied or []),
            meta=MetaPayload(
                analysis_duration_ms=analysis_duration_ms,
                engine_version=self.ENGINE_VERSION,
                coverage=CoveragePayload(
                    lines_total=metadata.total_entries or None,
                    errors_grouped=len(findings),
                ),
            ),
        )

        envelope_dict = self._masker.sanitize_structure(envelope.to_dict())
        markdown = self._masker.sanitize_text(
            self._compose_markdown(
                analysis=analysis,
                findings=envelope_dict.get("findings", []),
                overview=envelope_dict.get("overview", {}),
                quick_actions=envelope_dict.get("quick_actions", []),
                fix_steps=envelope_dict.get("full_fix_steps", []),
                checks=envelope_dict.get("checks", []),
                tips=envelope_dict.get("tips", []),
                user_query=user_query,
            )
        )

        return markdown, envelope, envelope_dict

    # ------------------------------------------------------------------
    # Markdown composition helpers

    def _compose_markdown(
        self,
        *,
        analysis: LogAnalysisResult,
        findings: List[Dict[str, Any]],
        overview: Dict[str, Any],
        quick_actions: List[Dict[str, Any]],
        fix_steps: List[Dict[str, Any]],
        checks: List[str],
        tips: List[str],
        user_query: Optional[str],
    ) -> str:
        findings = [
            item
            if isinstance(item, dict)
            else self._masker.sanitize_structure(asdict(item))
            for item in findings
        ]
        quick_actions = [
            item
            if isinstance(item, dict)
            else self._masker.sanitize_structure(asdict(item))
            for item in quick_actions
        ]
        fix_steps = [
            item
            if isinstance(item, dict)
            else self._masker.sanitize_structure(asdict(item))
            for item in fix_steps
        ]

        scope_parts = []
        time_range = overview.get("time_range")
        if time_range:
            scope_parts.append(time_range)
        files = overview.get("files") or []
        if files:
            scope_parts.append(f"{len(files)} file{'s' if len(files) != 1 else ''}")
        scope_line = " • ".join(scope_parts) if scope_parts else "Log bundle"

        env_parts = []
        if overview.get("app_version"):
            env_parts.append(f"Mailbird {overview['app_version']}")
        if overview.get("db_size"):
            env_parts.append(overview["db_size"])
        if overview.get("accounts_count"):
            env_parts.append(f"{overview['accounts_count']} account(s)")
        if overview.get("platform"):
            env_parts.append(overview["platform"])
        environment_line = " • ".join(env_parts) if env_parts else "Environment details not detected"

        top_issues = self._format_top_issues(findings)

        confidence_line = overview.get("confidence", "medium").capitalize()
        confidence_reason = overview.get("confidence_reason")
        if confidence_reason:
            confidence_line += f" — {confidence_reason}"

        intro_issue = findings[0]["title"] if findings else "the errors in your logs"
        empathetic_opening = (
            f"Thanks for sharing the log — I know {intro_issue.lower()} can be frustrating,"
            " but I dug through everything and have a clear plan for you."
        )

        overview_section = (
            "## Solution Overview\n\n"
            f"* **Scope analyzed:** {scope_line}\n"
            f"* **Environment:** {environment_line}\n"
            f"* **Top issue(s):** {top_issues}\n"
            f"* **Confidence:** {confidence_line}\n"
        )

        findings_lines = ["## What I found"]
        for finding in findings[:6]:
            severity = finding.get("severity", "medium").capitalize()
            findings_lines.append(
                f"* **[{severity}] {finding['title']}** — {finding['details']}"
            )
        findings_section = "\n".join(findings_lines)

        quick_section_lines = ["## Quick things to try (takes a minute)"]
        for index, action in enumerate(quick_actions[:4], start=1):
            quick_section_lines.append(f"{index}. {action['label']}")
        quick_section = "\n".join(quick_section_lines)

        fix_section_lines = ["## If the above steps does not help then please try this guided fix"]
        for index, step in enumerate(fix_steps[:7], start=1):
            fix_section_lines.append(f"{index}. {step['step']}")
        fix_section = "\n".join(fix_section_lines)

        good_to_know_lines = [self._derive_root_cause_summary(analysis)]
        good_to_know_lines.extend([f"* {item}" for item in checks[:4]])
        good_to_know_section = "## Good to know\n" + "\n".join(good_to_know_lines)
        tips_section = "## Helpful Tips\n" + "\n".join(f"* {item}" for item in tips[:4])

        closing = (
            "## Encouraging Wrap-up\n"
            "You’ve got this. Let me know how things look after Step 2 and we’ll iterate together."
        )

        parts = [
            empathetic_opening,
            overview_section,
            findings_section,
            quick_section,
            fix_section,
            good_to_know_section,
            tips_section,
            closing,
        ]

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Envelope data builders

    def _build_findings(self, analysis: LogAnalysisResult) -> List[FindingPayload]:
        patterns = sorted(
            analysis.error_patterns,
            key=lambda p: (self._pattern_severity_score(p), p.occurrences, p.confidence),
            reverse=True,
        )

        findings: List[FindingPayload] = []
        for pattern in patterns[:5]:
            severity = self._map_pattern_severity(pattern, analysis.root_causes)
            root_cause = self._match_root_cause(pattern, analysis.root_causes)
            details = self._build_finding_details(pattern, root_cause)

            signature_dict = pattern.signature or {}
            signature_obj = SignatureInfo(
                exception=signature_dict.get("exception"),
                message_fingerprint=signature_dict.get("message_fingerprint"),
                top_frames=signature_dict.get("top_frames", []) or [],
            )

            evidence_refs: List[EvidenceReference] = []
            for ref in pattern.evidence_refs[:3]:
                try:
                    evidence_refs.append(EvidenceReference(**ref))
                except TypeError:
                    continue

            findings.append(
                FindingPayload(
                    severity=severity,
                    title=self._masker.sanitize_text(pattern.description),
                    details=self._masker.sanitize_text(details),
                    evidence_refs=evidence_refs,
                    occurrences=pattern.occurrences,
                    signature=signature_obj,
                )
            )

        return findings

    def _build_finding_details(self, pattern: ErrorPattern, root_cause: Optional[RootCause]) -> str:
        components = ", ".join(sorted(pattern.affected_components)) if pattern.affected_components else "the app"
        window = self._format_time_window(pattern.first_seen, pattern.last_seen)
        base = (
            f"{pattern.description}. Seen {pattern.occurrences} time(s) in {components}"
            f" between {window}."
        )
        if root_cause:
            base += f" Likely root cause: {root_cause.title.lower()} with {int(root_cause.confidence_score * 100)}% confidence."
        return base

    def _derive_quick_actions(self, analysis: LogAnalysisResult) -> List[QuickActionPayload]:
        actions: List[str] = []
        actions.extend(analysis.recommendations[:4])

        if not actions:
            actions = [
                "Restart Mailbird to clear any stuck sessions.",
                "Toggle the affected account offline and back online to re-sync.",
                "Run Mailbird’s database maintenance (compact/repair).",
            ]

        payloads: List[QuickActionPayload] = []
        for label in actions[:4]:
            action_id = self._slugify(label)
            payloads.append(
                QuickActionPayload(
                    label=self._masker.sanitize_text(label.rstrip('.')),
                    action_id=action_id,
                    kind="manual",
                    notes=None,
                )
            )
        return payloads

    def _derive_fix_steps(self, analysis: LogAnalysisResult) -> List[FixStepPayload]:
        steps: List[str] = []
        for cause in analysis.root_causes:
            for step in cause.resolution_steps:
                if step not in steps:
                    steps.append(step)
        if not steps:
            steps = [
                "Confirm the server settings (host, port, TLS) match your email provider.",
                "Update Mailbird to the latest build and reboot the device.",
                "Rebuild the message index to clear stale sync state.",
            ]

        return [
            FixStepPayload(step=self._masker.sanitize_text(step.rstrip('.')), notes=None)
            for step in steps[:7]
        ]

    def _derive_extra_checks(self, analysis: LogAnalysisResult) -> List[str]:
        checks: List[str] = []
        if analysis.performance_metrics.ui_freezes:
            checks.append("Open a previously frozen window to confirm it responds within a few seconds.")
        if analysis.performance_metrics.crash_events:
            checks.append("Review the Windows Event Viewer to ensure no new Mailbird crashes logged after the fix.")
        checks.append("Send a test email from the affected account and confirm it arrives within 2 minutes.")
        checks.append("Watch the sync status for five minutes to ensure no new error banners appear.")
        return checks[:4]

    def _derive_tips(self, analysis: LogAnalysisResult) -> List[str]:
        tips = list(analysis.recommendations[:4])
        if not tips:
            tips = [
                "Schedule a monthly database compact to keep the store under control.",
                "Keep provider SSL/TLS requirements handy — they change more often than expected.",
                "Archive large attachments or move them to cloud storage to trim sync load.",
            ]
        return tips[:4]

    # ------------------------------------------------------------------
    # Utility helpers

    def _map_confidence(self, score: float) -> StructuredConfidence:
        if score >= 0.75:
            return StructuredConfidence.HIGH
        if score >= 0.45:
            return StructuredConfidence.MEDIUM
        return StructuredConfidence.LOW

    def _confidence_reason(
        self,
        level: StructuredConfidence,
        analysis: LogAnalysisResult,
        findings: Sequence[Dict[str, Any]],
    ) -> str:
        if level is StructuredConfidence.HIGH:
            return "Repeated signature across the log window with consistent stack frames."
        if level is StructuredConfidence.MEDIUM:
            return "Multiple contributing patterns detected; plan covers the dominant ones first."
        if findings:
            return "Evidence is limited, so we’re proceeding with the safest fixes first."
        return "Logs were sparse; continuing with conservative guidance."

    def _map_pattern_severity(
        self,
        pattern: ErrorPattern,
        root_causes: Sequence[RootCause],
    ) -> FindingSeverity:
        matched = self._match_root_cause(pattern, root_causes)
        if matched:
            if matched.impact in (IssueImpact.CRITICAL, IssueImpact.HIGH):
                return FindingSeverity.HIGH
            if matched.impact is IssueImpact.MEDIUM:
                return FindingSeverity.MEDIUM
            return FindingSeverity.LOW

        if pattern.category in {ErrorCategory.DATABASE, ErrorCategory.AUTHENTICATION, ErrorCategory.SYNCHRONIZATION, ErrorCategory.NETWORK}:
            if pattern.occurrences >= 2 or pattern.confidence >= 0.6:
                return FindingSeverity.HIGH
        if pattern.occurrences >= 3 or pattern.confidence >= 0.5:
            return FindingSeverity.MEDIUM
        return FindingSeverity.LOW

    def _pattern_severity_score(self, pattern: ErrorPattern) -> float:
        base = pattern.confidence
        if pattern.category in {ErrorCategory.DATABASE, ErrorCategory.AUTHENTICATION}:
            base += 0.2
        base += min(pattern.occurrences / 10.0, 0.3)
        return base

    def _match_root_cause(
        self,
        pattern: ErrorPattern,
        root_causes: Sequence[RootCause],
    ) -> Optional[RootCause]:
        for cause in root_causes:
            if pattern.pattern_id in (cause.related_patterns or []):
                return cause
        for cause in root_causes:
            if cause.category == pattern.category:
                return cause
        return None

    def _format_time_range(self, metadata: LogMetadata) -> Optional[str]:
        start = metadata.session_start
        end = metadata.session_end
        if start and end:
            if start.date() == end.date():
                return f"{start.strftime('%Y-%m-%d %H:%M')} → {end.strftime('%H:%M')}"
            return f"{start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}"
        if start:
            return start.strftime('%Y-%m-%d %H:%M')
        return None

    def _format_db_size(self, metadata: LogMetadata) -> Optional[str]:
        if metadata.database_size_mb:
            size = metadata.database_size_mb
            if size >= 1024:
                return f"≈{size / 1024:.1f} GB"
            return f"≈{size:.0f} MB"
        return None

    def _format_time_window(self, start: datetime, end: datetime) -> str:
        if start.date() == end.date():
            return f"{start.strftime('%Y-%m-%d %H:%M')} and {end.strftime('%H:%M')}"
        return f"{start.strftime('%Y-%m-%d %H:%M')} and {end.strftime('%Y-%m-%d %H:%M')}"

    def _safe_value(self, value: Optional[str], invalid: Iterable[str]) -> Optional[str]:
        if not value:
            return None
        if value.strip().lower() in invalid:
            return None
        return value

    def _format_top_issues(self, findings: Sequence[Dict[str, Any]]) -> str:
        if not findings:
            return "No blocking issues detected"
        formatted = []
        for finding in findings[:3]:
            severity = finding.get("severity", "medium").capitalize()
            formatted.append(f"[{severity}] {finding['title']}")
        return "; ".join(formatted)

    def _derive_root_cause_summary(self, analysis: LogAnalysisResult) -> str:
        if not analysis.root_causes:
            return (
                "I saw recurring errors but no single dominant trigger."
                " The steps above refresh the pipeline and harden sync reliability."
            )
        top = analysis.top_priority_cause or analysis.root_causes[0]
        return (
            f"Most of the noise comes from {top.title.lower()}, which lines up with"
            f" the frames in the log. The fix plan resets that component and"
            " clears out the stale state that causes the loop."
        )

    def _slugify(self, text: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
        return slug or "action"
