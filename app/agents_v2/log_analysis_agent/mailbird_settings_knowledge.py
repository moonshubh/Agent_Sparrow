"""
Mailbird Settings Knowledge Base for Log Analysis Agent
This module provides the log analysis agent with knowledge of valid Mailbird settings
to ensure accurate recommendations and avoid suggesting non-existent settings.
"""

MAILBIRD_SETTINGS = {
    "General": {
        "Application_behavior": {
            "settings": [
                "Run on Windows startup",
                "Start minimized",
                "Hide taskbar icon when minimized",
                "Quit Mailbird on close",
                "Use Gmail keyboard shortcuts"
            ],
            "description": "Controls how Mailbird behaves on system startup and window management"
        },
        "Notifications": {
            "settings": [
                "Show unread count in taskbar & system tray",
                "Show tray notification when receiving a message",
                "Show tray notification when a message with Email Tracking is opened",
                "New message sound"
            ],
            "options": {
                "New message sound": ["Default (Chirp)", "Custom", "None"]
            },
            "description": "Manages notification preferences and sounds"
        },
        "Language": {
            "settings": ["Language"],
            "options": {
                "Language": ["English", "Spanish", "French", "German", "Italian", "Portuguese", "Dutch", "Russian", "Japanese", "Korean"]
            },
            "description": "Interface language selection"
        }
    },
    
    "Appearance": {
        "Layout_and_theme": {
            "settings": [
                "Layout selector",
                "Show reading pane",
                "Show folders separately in expanded navigation pane",
                "Theme",
                "Theme color"
            ],
            "options": {
                "Theme": ["Light theme", "Dark theme", "Full dark theme"]
            },
            "description": "Visual appearance and layout configuration"
        },
        "Background": {
            "settings": ["Background gallery"],
            "description": "Background image selection"
        },
        "Interface": {
            "settings": [
                "Show welcome message",
                "Show Inbox Zero",
                "Show share buttons"
            ],
            "description": "UI element visibility"
        },
        "Conversations": {
            "settings": [
                "Group unread conversations at the top",
                "Show 'important mail' indicator"
            ],
            "description": "Conversation display preferences"
        },
        "Messages": {
            "settings": [
                "Group messages into conversations",
                "Show message previews in conversation view",
                "Always show remote images",
                "Mark messages as read"
            ],
            "options": {
                "Mark messages as read": "Slider from Never to Immediately"
            },
            "description": "Message display and grouping settings"
        }
    },
    
    "Scaling": {
        "settings": [
            "Application scaling level",
            "Email scaling level",
            "Apps scaling level",
            "Text formatting mode"
        ],
        "options": {
            "Text formatting mode": ["Ideal", "Compact", "Comfortable"]
        },
        "description": "UI scaling for different screen resolutions and preferences"
    },
    
    "Composing": {
        "Composing_font": {
            "settings": [
                "Font family",
                "Font size"
            ],
            "description": "Default font settings for composing emails"
        },
        "Compose_window": {
            "settings": [
                "Show 'send & archive' button",
                "Show sender & recipient details only when cursor is on address field",
                "Show Cc and Bcc by default",
                "Collapse message by default when replying",
                "Auto-add recipients when @ tagging"
            ],
            "description": "Email composition window behavior"
        },
        "Sending": {
            "settings": [
                "Enable Email Tracking by default",
                "Add new recipients to Contacts",
                "Undo send period"
            ],
            "options": {
                "Undo send period": "0-30 seconds slider"
            },
            "description": "Email sending preferences and features"
        },
        "In_line_reply": {
            "settings": [
                "Enable in-line reply",
                "Prefix field"
            ],
            "description": "In-line reply configuration"
        },
        "Quick_compose": {
            "settings": ["Quick compose shortcut"],
            "description": "Keyboard shortcut for quick compose"
        }
    },
    
    "Accounts": {
        "settings": [
            "Accounts list",
            "Enable unified account",
            "Select on startup"
        ],
        "description": "Email account management and unified inbox settings"
    },
    
    "Identities": {
        "settings": [
            "Identities & signatures",
            "Add signatures to new conversations only"
        ],
        "description": "Email identities and signature management"
    },
    
    "Folders": {
        "settings": [
            "Account selector",
            "Folder tree",
            "Sync with server"
        ],
        "description": "Email folder management and synchronization"
    },
    
    "Filters": {
        "settings": [
            "Filters list",
            "Blocked senders list"
        ],
        "description": "Email filtering rules and blocked senders"
    },
    
    "Updates": {
        "settings": [
            "Update settings",
            "Become an early adopter"
        ],
        "options": {
            "Update settings": [
                "Install updates automatically",
                "Download updates, ask before installing",
                "Never check for updates"
            ]
        },
        "description": "Application update preferences"
    },
    
    "Network": {
        "Proxy_server": {
            "settings": [
                "Proxy settings",
                "Proxy requires authentication"
            ],
            "description": "Network proxy configuration"
        }
    },
    
    "Snoozes": {
        "Weekly_schedule": {
            "settings": [
                "My day starts at",
                "My weekend starts at",
                "My workday ends at",
                "My week starts on",
                "My weekend starts on"
            ],
            "description": "Snooze scheduling based on work week"
        },
        "Snooze_preferences": {
            "settings": [
                "Later today",
                "Someday"
            ],
            "options": {
                "Later today": "In X hours",
                "Someday": "In X days/weeks/months"
            },
            "description": "Default snooze durations"
        }
    },
    
    "Advanced": {
        "Archiving": {
            "settings": ["Auto-select next conversation when archiving"],
            "description": "Archive behavior settings"
        },
        "Sync_behavior": {
            "settings": [
                "Download messages on demand",
                "Attachment auto-download limit"
            ],
            "description": "Email synchronization and attachment handling"
        },
        "Default_email": {
            "settings": ["Tell me if Mailbird is not the default email client"],
            "description": "Default email client detection"
        },
        "Performance": {
            "settings": [
                "Show animations",
                "Enable hardware rendering"
            ],
            "description": "Performance and rendering options"
        },
        "Telemetry": {
            "settings": ["Share performance and usage data"],
            "description": "Anonymous usage statistics"
        }
    }
}

def get_mailbird_settings_context():
    """
    Returns a formatted string of Mailbird settings for the LLM context.
    """
    context = """
## Valid Mailbird Settings Reference

When analyzing logs and providing recommendations, only suggest settings that actually exist in Mailbird.
Here are the valid settings categories and options:

### General Settings
- Application behavior: Run on startup, minimize options, taskbar behavior, Gmail shortcuts
- Notifications: Unread count, tray notifications, message sounds
- Language selection

### Appearance Settings  
- Themes: Light, Dark, Full Dark
- Layout options: Reading pane, folder display
- Interface elements: Welcome message, Inbox Zero, share buttons
- Conversation grouping and message preview options
- Remote image display settings

### Scaling Settings
- Application, Email, and Apps scaling levels (percentage sliders)
- Text formatting modes: Ideal, Compact, Comfortable

### Composing Settings
- Font family and size selection
- Compose window behavior: Cc/Bcc display, collapse replies
- Email tracking and undo send (0-30 seconds)
- In-line reply with prefix customization

### Account Management
- Multiple account support with unified inbox option
- Identity and signature management
- Folder synchronization settings

### Filters and Rules
- Email filters configuration
- Blocked senders management

### Network Settings
- Proxy server configuration with authentication support

### Snooze Settings
- Work schedule configuration
- Customizable snooze durations

### Advanced Settings
- Archive behavior
- Message download and attachment handling
- Hardware rendering and animations
- Default email client detection

### Update Settings
- Automatic, manual, or disabled updates
- Early adopter program

Note: When recommending settings changes, always use the exact setting names listed above.
Never suggest settings that don't exist in this list.
"""
    return context

def validate_setting_recommendation(setting_path: str) -> bool:
    """
    Validates if a recommended setting actually exists in Mailbird.
    
    Args:
        setting_path: The setting path like "General.Notifications.Show unread count"
        
    Returns:
        bool: True if the setting exists, False otherwise
    """
    parts = setting_path.split('.')
    current = MAILBIRD_SETTINGS
    
    for part in parts:
        if isinstance(current, dict):
            # Try both with underscores and spaces
            key = part.replace(' ', '_')
            if key in current:
                current = current[key]
            elif part in current:
                current = current[part]
            else:
                # Check in settings lists
                for k, v in current.items():
                    if isinstance(v, dict) and 'settings' in v:
                        if part in v['settings']:
                            return True
                return False
        elif isinstance(current, list):
            return part in current
    
    return True

def get_setting_options(setting_path: str) -> list:
    """
    Get valid options for a specific setting if it has predefined options.
    
    Args:
        setting_path: The setting path
        
    Returns:
        list: List of valid options or empty list if no options defined
    """
    # Implementation would traverse the settings structure
    # and return options if they exist
    return []