import re
from typing import List, Optional, Dict, Any, Pattern
from app.schemas.qa_schemas import LogEntry, IdentifiedError

# Regex to capture Mailbird version and DB size
MAILBIRD_VERSION_DB_PATTERN = re.compile(
    r"Mailbird\.exe \[(?P<version>[^\]]+)\]\s*\[[^\]]+\]\s*\[Store\.db (?P<dbsize>[^\]]+)\]"
)

# Regex to capture accounts count
ACCOUNTS_INFO_PATTERN = re.compile(
    r"Accounts: (?P<accounts>\d+)\."
)

# Regex for shutdown line (optional, for more complex scenarios)
SHUTDOWN_PATTERN = re.compile(r"Shutting down\. Code:")

def extract_mailbird_metadata_from_log_lines(log_lines: List[str]) -> Dict[str, Any]:
    """
    Extracts Mailbird version, DB size, and account count from a list of log lines.
    It prioritizes the last found entries for version/DB and accounts,
    assuming these might be updated during a Mailbird session.
    """
    metadata = {
        "mailbird_version": None,
        "database_size": None,
        "accounts_count": None,
    }
    # Use a temporary dict to store the latest findings before a shutdown or end of log
    current_session_metadata = {}

    for line in log_lines:
        version_match = MAILBIRD_VERSION_DB_PATTERN.search(line)
        if version_match:
            current_session_metadata["mailbird_version"] = version_match.group("version")
            current_session_metadata["database_size"] = version_match.group("dbsize")

        accounts_match = ACCOUNTS_INFO_PATTERN.search(line)
        if accounts_match:
            try:
                current_session_metadata["accounts_count"] = int(accounts_match.group("accounts"))
            except ValueError:
                # Handle case where 'accounts' is not a valid integer, though regex ensures digits
                pass # Or log a warning

        # If a shutdown line is encountered, we might consider the current_session_metadata
        # as final for that "session" within the log. For simplicity, we'll just
        # let the last found values overall be the final ones.
        # if SHUTDOWN_PATTERN.search(line):
        #     # If there's data in current_session_metadata, update metadata and clear current_session_metadata
        #     # This logic can be more complex if multiple sessions are expected in one log file.
        #     pass

    # Update final metadata with the last found (or only) values
    if "mailbird_version" in current_session_metadata:
        metadata["mailbird_version"] = current_session_metadata["mailbird_version"]
    if "database_size" in current_session_metadata:
        metadata["database_size"] = current_session_metadata["database_size"]
    if "accounts_count" in current_session_metadata:
        metadata["accounts_count"] = current_session_metadata["accounts_count"]
        
    return metadata

from datetime import datetime

# Basic regex to capture common log patterns: timestamp, level, message
LOG_PATTERN_SIMPLE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.\d{1,6})\|"
    r"(?P<level>[A-Z]+)\|"
    r"(?P<source>[^|]+)\|"
    r"[^|]+\|"
    r"[^|]+\|"
    r"(?P<message>[^|]*)(?:\|)?$"
)

def parse_log_string_to_log_entry(log_string: str) -> Optional[LogEntry]:
    """
    Parses a single log string that is expected to be a new log entry.
    Returns a LogEntry object if parsing is successful, otherwise None.
    """
    match = LOG_PATTERN_SIMPLE.match(log_string)
    if match:
        data = match.groupdict()
        timestamp_str = data.get("timestamp")
        parsed_timestamp = datetime.utcnow() # Default to now
        if timestamp_str:
            try:
                # Attempt to normalize and parse the timestamp
                ts = timestamp_str.replace(" ", "T") # Replace space with T for ISO format
                if '.' in ts:
                    ts = ts.split('.', 1)[0] # Remove fractional seconds if present, for simplicity
                if 'Z' in ts:
                    ts = ts.replace('Z', '') # Remove Z for UTC indication if present
                parsed_timestamp = datetime.fromisoformat(ts)
            except ValueError:
                # Fallback if specific parsing fails, but keep it as a warning
                # print(f"Warning: Could not parse timestamp '{timestamp_str}', using current UTC time.")
                pass # Keep parsed_timestamp as utcnow if specific format fails

        return LogEntry(
            timestamp=parsed_timestamp,
            level=(data.get("level") or "UNKNOWN").upper(),
            source=data.get("source"),
            message=data.get("message", log_string).strip(),
            details=None # Initialized with no details
        )
    return None # Indicates the line is not a new, parsable log entry

def parse_log_lines_to_log_entries(raw_log_lines: List[str]) -> List[LogEntry]:
    """
    Parses a list of raw log strings, handling multi-line entries.
    """
    log_entries: List[LogEntry] = []
    current_entry: Optional[LogEntry] = None

    for line_content in raw_log_lines:
        if not line_content.strip(): # Skip empty lines
            continue

        parsed_as_new_entry = parse_log_string_to_log_entry(line_content)

        if parsed_as_new_entry:
            if current_entry: # Finalize the previous entry before starting a new one
                log_entries.append(current_entry)
            current_entry = parsed_as_new_entry
        else: # It's a continuation line or unparseable
            if current_entry:
                if current_entry.details:
                    current_entry.details += "\n" + line_content
                else:
                    current_entry.details = line_content
            else:
                # This line is not a new entry and there's no current entry to append to.
                # Treat as an unparseable standalone line.
                log_entries.append(
                    LogEntry(
                        timestamp=datetime.utcnow(), # Or try to find a timestamp if possible
                        level="UNPARSEABLE",
                        message=line_content,
                        source="OrphanedContinuationLine"
                    )
                )
    
    if current_entry: # Append the last processed entry
        log_entries.append(current_entry)
    
    return log_entries

def identify_issues_in_log_entry(
    log_entry: LogEntry,
    custom_error_patterns: Optional[Dict[str, Pattern[str]]] = None
) -> List[IdentifiedError]:
    """
    Analyzes a single LogEntry (which may have multi-line details) 
    to identify errors and notable patterns.
    """
    identified_errors: List[IdentifiedError] = []
    generic_error_levels = {"ERROR", "CRITICAL"}

    # Combine message and details for comprehensive searching
    full_text_to_search = log_entry.message
    if log_entry.details:
        full_text_to_search += "\n" + log_entry.details

    # Check for custom error patterns
    if custom_error_patterns:
        for error_type, pattern in custom_error_patterns.items():
            if pattern.search(full_text_to_search):
                # Avoid duplicate reporting if a generic error for the same log is also found
                is_duplicate = any(
                    err.error_type == error_type and log_entry in err.offending_logs
                    for err in identified_errors
                )
                if not is_duplicate:
                    identified_errors.append(
                        IdentifiedError(
                            error_type=error_type,
                            description=f"Custom pattern '{pattern.pattern}' matched. Log: {full_text_to_search[:500]}...", # Truncate for brevity
                            offending_logs=[log_entry]
                        )
                    )

    # Check for generic errors by log level (e.g., ERROR, CRITICAL)
    if log_entry.level.upper() in generic_error_levels:
        # Avoid reporting if a custom pattern already covered this specific log entry's primary message
        # This check is a bit simplistic; a more robust way might involve checking if any custom error
        # for THIS log_entry has already been added.
        already_reported_by_custom_for_this_log = any(
            log_entry in err.offending_logs for err in identified_errors
        )
        if not already_reported_by_custom_for_this_log:
            identified_errors.append(
                IdentifiedError(
                    error_type=f"Generic{log_entry.level.capitalize()}Found",
                    description=f"Log entry with level {log_entry.level}. Content: {full_text_to_search[:500]}...", # Truncate
                    offending_logs=[log_entry]
                )
            )
    
    # Example: A specific check for 'timeout' that might not be a formal 'ERROR' level
    # This can be expanded or made more generic.
    if "timeout" in full_text_to_search.lower():
        already_reported = any(log_entry in err.offending_logs for err in identified_errors)
        if not already_reported:
                identified_errors.append(
                IdentifiedError(
                    error_type="PotentialTimeoutDetected", # More specific than just 'TimeoutDetected'
                    description=f"Potential timeout keyword found. Log: {full_text_to_search[:500]}...", # Truncate
                    offending_logs=[log_entry],
                    suggested_action="Investigate service response times related to this log entry."
                )
            )

    return identified_errors
