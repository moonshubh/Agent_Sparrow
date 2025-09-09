import re
from typing import Dict, List, Optional, Any
from datetime import datetime

# Regex for the Mailbird log format. It captures the timestamp, level, and the initial message.
# It's designed to match the start of a new log entry.
LOG_START_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.\d{4})\|"
    r"(?P<level>[A-Z]+)\|"
    r"(?P<thread_id>\d+)\|"
    r"(?P<source_info_1>\d+)\|"
    r"(?P<source_info_2>\d+)\|"
    r"(?P<message>.*?)(?=\||$)" # Non-greedy match for the message
)

def parse_log_content(log_content: str) -> Dict[str, Any]:
    """
    Parses raw Mailbird log content into a structured format, handling multi-line entries
    and extracting key system metadata.

    Args:
        log_content: The raw string content of the log file.

    Returns:
        A dictionary containing a list of structured log entries and detailed metadata.
    """
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
                "message": data.get("message", "").strip(),
                "details": []
            }
        elif current_entry_dict:
            current_entry_dict["details"].append(line.strip())

    if current_entry_dict:
        structured_entries.append(current_entry_dict)

    for entry in structured_entries:
        entry["details"] = "\n".join(entry["details"])

    # --- Metadata Extraction ---
    version_pattern = re.compile(r"Mailbird(?:\s+Version)?\s*(?P<version>\d+\.\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)
    db_size_pattern = re.compile(r"Database\s+size\s*[:=]\s*(?P<size>[\d\.]+\s*(?:KB|MB|GB))", re.IGNORECASE)
    accounts_pattern = re.compile(r"Accounts?\s*[:=]\s*(?P<accounts>\d+)", re.IGNORECASE)
    folders_pattern = re.compile(r"Folders?\s*[:=]\s*(?P<folders>\d+)", re.IGNORECASE)

    version, db_size, accounts, folders = None, None, None, None

    for line in raw_lines:
        if not version and (m := version_pattern.search(line)):
            version = m.group("version")
        if not db_size and (m := db_size_pattern.search(line)):
            db_size = m.group("size")
        if not accounts and (m := accounts_pattern.search(line)):
            accounts = m.group("accounts")
        if not folders and (m := folders_pattern.search(line)):
            folders = m.group("folders")
        if all((version, db_size, accounts, folders)):
            break
    
    # --- Calculate Log Timeframe ---
    log_timeframe = "Unknown"
    if structured_entries:
        timestamps = [
            datetime.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S.%f")
            for entry in structured_entries if entry.get("timestamp")
        ]
        if timestamps:
            min_ts = min(timestamps)
            max_ts = max(timestamps)
            log_timeframe = f"{min_ts.strftime('%Y-%m-%d %H:%M:%S')} to {max_ts.strftime('%Y-%m-%d %H:%M:%S')}"

    # --- Prepare Final Parsed Data ---
    parsed_data = {
        "entries": structured_entries,
        "metadata": {
            "total_lines_processed": len(raw_lines),
            "total_entries_parsed": len(structured_entries),
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "parser_version": "2.0.0", # Updated version
            "parser_notes": "Mailbird-specific log parser, v2 with enhanced metadata.",
            "mailbird_version": version or "Unknown",
            "database_size_mb": db_size or "Unknown",
            "account_count": str(accounts) if accounts is not None else "Unknown",
            "folder_count": str(folders) if folders is not None else "Unknown",
            "log_timeframe": log_timeframe,
        }
    }

    return parsed_data

