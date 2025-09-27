"""
Markdown Builder Utilities

Provides a fluent interface for generating well-formatted markdown content
with proper escaping, styling, and structure for log analysis responses.
"""

from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import re
from urllib.parse import quote


class MarkdownStyle(Enum):
    """Markdown styling options"""
    BOLD = "**"
    ITALIC = "_"
    CODE = "`"
    STRIKETHROUGH = "~~"
    UNDERLINE = "__"


class AlertLevel(Enum):
    """Alert box levels for important messages"""
    INFO = "ℹ️"
    SUCCESS = "✅"
    WARNING = "⚠️"
    ERROR = "❌"
    CRITICAL = "🚨"


@dataclass
class TableRow:
    """Represents a row in a markdown table"""
    cells: List[str]


class MarkdownBuilder:
    """
    Fluent interface for building markdown content.

    Provides methods for creating headers, paragraphs, lists, tables,
    code blocks, and special formatting with proper escaping.
    """

    def __init__(self):
        """Initialize the markdown builder"""
        self.content: List[str] = []
        self._indentation_level: int = 0
        self._list_stack: List[str] = []  # Track nested list types

    def add_header(self, text: str, level: int = 1) -> "MarkdownBuilder":
        """
        Add a header to the markdown.

        Args:
            text: Header text
            level: Header level (1-6)

        Returns:
            Self for method chaining
        """
        if not 1 <= level <= 6:
            raise ValueError(f"Header level must be 1-6, got {level}")

        header = "#" * level + " " + self._escape_text(text)
        self.content.append(header)
        return self

    def add_paragraph(self, text: str, style: Optional[MarkdownStyle] = None) -> "MarkdownBuilder":
        """
        Add a paragraph with optional styling.

        Args:
            text: Paragraph text
            style: Optional markdown style

        Returns:
            Self for method chaining
        """
        # Escape text to prevent markdown injection
        escaped_text = self._escape_text(text)

        if style:
            escaped_text = f"{style.value}{escaped_text}{style.value}"

        self.content.append(escaped_text)
        self.content.append("")  # Empty line after paragraph
        return self

    def add_alert_box(self, message: str, level: AlertLevel = AlertLevel.INFO) -> "MarkdownBuilder":
        """
        Add an alert box with an icon.

        Args:
            message: Alert message
            level: Alert level

        Returns:
            Self for method chaining
        """
        box = f"> {level.value} **{level.name}**: {self._escape_text(message)}"
        self.content.append(box)
        self.content.append("")
        return self

    def add_metadata_box(self, metadata: Dict[str, Any]) -> "MarkdownBuilder":
        """
        Add a formatted metadata box.

        Args:
            metadata: Dictionary of metadata key-value pairs

        Returns:
            Self for method chaining
        """
        self.content.append("```yaml")
        self.content.append("# System Information")

        for key, value in metadata.items():
            formatted_key = key.replace("_", " ").title()
            self.content.append(f"{formatted_key}: {value}")

        self.content.append("```")
        self.content.append("")
        return self

    def add_code_block(self, code: str, language: str = "log",
                       line_numbers: bool = False,
                       highlight_lines: Optional[List[int]] = None) -> "MarkdownBuilder":
        """
        Add a code block with optional syntax highlighting.

        Args:
            code: Code content
            language: Language for syntax highlighting
            line_numbers: Whether to show line numbers
            highlight_lines: Lines to highlight

        Returns:
            Self for method chaining
        """
        self.content.append(f"```{language}")

        lines = code.split("\n")
        for i, line in enumerate(lines, 1):
            if line_numbers:
                line_prefix = f"{i:4d} | "
            else:
                line_prefix = ""

            if highlight_lines and i in highlight_lines:
                # Add highlighting marker
                line_content = f">>> {line_prefix}{line} <<<"
            else:
                line_content = f"{line_prefix}{line}"

            self.content.append(line_content)

        self.content.append("```")
        self.content.append("")
        return self

    def add_list(self, items: List[str], ordered: bool = False,
                 nested_level: int = 0) -> "MarkdownBuilder":
        """
        Add a bulleted or numbered list.

        Args:
            items: List items
            ordered: Whether to use numbered list
            nested_level: Indentation level for nested lists

        Returns:
            Self for method chaining
        """
        indent = "  " * nested_level

        for i, item in enumerate(items, 1):
            if ordered:
                marker = f"{i}."
            else:
                marker = "-"

            self.content.append(f"{indent}{marker} {self._escape_text(item)}")

        self.content.append("")
        return self

    def add_table(self, headers: List[str], rows: List[TableRow]) -> "MarkdownBuilder":
        """
        Add a formatted table.

        Args:
            headers: Table headers
            rows: Table rows

        Returns:
            Self for method chaining
        """
        # Add headers
        header_line = "| " + " | ".join(self._escape_text(h) for h in headers) + " |"
        self.content.append(header_line)

        # Add separator
        separator = "|" + "|".join([" --- " for _ in headers]) + "|"
        self.content.append(separator)

        # Add rows
        for row in rows:
            if len(row.cells) != len(headers):
                raise ValueError(f"Row has {len(row.cells)} cells, expected {len(headers)}")

            row_line = "| " + " | ".join(self._escape_text(cell) for cell in row.cells) + " |"
            self.content.append(row_line)

        self.content.append("")
        return self

    def add_horizontal_rule(self) -> "MarkdownBuilder":
        """
        Add a horizontal rule.

        Returns:
            Self for method chaining
        """
        self.content.append("---")
        self.content.append("")
        return self

    def add_collapsible_section(self, title: str, content: str) -> "MarkdownBuilder":
        """
        Add a collapsible details section.

        Args:
            title: Section title
            content: Section content

        Returns:
            Self for method chaining
        """
        self.content.append("<details>")
        self.content.append(f"<summary>{self._escape_html(title)}</summary>")
        self.content.append("")
        self.content.append(content)
        self.content.append("")
        self.content.append("</details>")
        self.content.append("")
        return self

    def add_link(self, text: str, url: str, title: Optional[str] = None) -> "MarkdownBuilder":
        """
        Add a hyperlink.

        Args:
            text: Link text
            url: Link URL
            title: Optional link title (shown on hover)

        Returns:
            Self for method chaining
        """
        escaped_text = self._escape_text(text)

        # Encode URL for special characters and spaces
        # But don't encode if it's already encoded (contains %20, %2F, etc.)
        if not re.search(r'%[0-9A-Fa-f]{2}', url):
            # Replace spaces with %20 for proper URL encoding
            url = url.replace(' ', '%20')

        if title:
            # Escape title to prevent markdown injection
            escaped_title = title.replace('"', '\\"')
            link = f'[{escaped_text}]({url} "{escaped_title}")'
        else:
            link = f"[{escaped_text}]({url})"

        self.content.append(link)
        return self

    def add_image(self, alt_text: str, url: str, title: Optional[str] = None) -> "MarkdownBuilder":
        """
        Add an image.

        Args:
            alt_text: Alternative text for the image
            url: Image URL
            title: Optional image title

        Returns:
            Self for method chaining
        """
        escaped_alt = self._escape_text(alt_text)

        # Encode URL for special characters and spaces
        if not re.search(r'%[0-9A-Fa-f]{2}', url):
            url = url.replace(' ', '%20')

        if title:
            # Escape title to prevent markdown injection
            escaped_title = title.replace('"', '\\"')
            image = f'![{escaped_alt}]({url} "{escaped_title}")'
        else:
            image = f"![{escaped_alt}]({url})"

        self.content.append(image)
        self.content.append("")
        return self

    def add_badge(self, label: str, value: str, color: str = "blue") -> "MarkdownBuilder":
        """
        Add a status badge (shields.io style).

        Args:
            label: Badge label
            value: Badge value
            color: Badge color

        Returns:
            Self for method chaining
        """
        # URL encode label and value for shields.io
        encoded_label = quote(label, safe='')
        encoded_value = quote(value, safe='')
        encoded_color = quote(color, safe='')

        # Using shields.io format with proper encoding
        badge_url = f"https://img.shields.io/badge/{encoded_label}-{encoded_value}-{encoded_color}"
        self.add_image(f"{label}: {value}", badge_url)
        return self

    def add_progress_bar(self, current: int, total: int, label: str = "") -> "MarkdownBuilder":
        """
        Add a text-based progress bar.

        Args:
            current: Current progress value
            total: Total value
            label: Optional label

        Returns:
            Self for method chaining
        """
        # Calculate percentage and clamp to 0-100 range
        if total > 0:
            percentage = int((current / total) * 100)
            percentage = max(0, min(100, percentage))  # Clamp to 0-100
        else:
            percentage = 0

        filled = int(percentage / 5)  # 20 segments total
        empty = 20 - filled

        bar = "█" * filled + "░" * empty
        progress_text = f"{label}: [{bar}] {percentage}% ({current}/{total})"

        self.content.append(f"`{progress_text}`")
        self.content.append("")
        return self

    def add_raw(self, content: str) -> "MarkdownBuilder":
        """
        Add raw markdown content without processing.

        Args:
            content: Raw markdown content

        Returns:
            Self for method chaining
        """
        self.content.append(content)
        return self

    def build(self) -> str:
        """
        Build the final markdown string.

        Returns:
            Complete markdown document
        """
        return "\n".join(self.content)

    def _escape_text(self, text: str) -> str:
        """
        Escape special markdown characters in text.

        Args:
            text: Text to escape

        Returns:
            Escaped text
        """
        # Escape markdown special characters
        special_chars = r"*_`~[]()#+-.!|{}"
        for char in special_chars:
            text = text.replace(char, f"\\{char}")
        return text

    def _escape_html(self, text: str) -> str:
        """
        Escape HTML special characters.

        Args:
            text: Text to escape

        Returns:
            HTML-escaped text
        """
        replacements = {
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        }

        for char, replacement in replacements.items():
            text = text.replace(char, replacement)

        return text

    def clear(self) -> "MarkdownBuilder":
        """
        Clear all content.

        Returns:
            Self for method chaining
        """
        self.content = []
        self._indentation_level = 0
        self._list_stack = []
        return self