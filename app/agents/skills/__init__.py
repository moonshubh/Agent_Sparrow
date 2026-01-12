"""
Skills loader for DeepAgents.
Discovers and loads SKILL.md files from project root (.sparrow/skills/).
Implements progressive disclosure: metadata first, full content on demand.
Enhanced with context-aware auto-detection for all skill categories.
"""
import re
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Pattern
import logging

logger = logging.getLogger(__name__)

# Skill auto-detection triggers: keyword patterns -> skill names
# When message matches pattern, skill content is auto-injected
SKILL_TRIGGERS: dict[str, list[str]] = {
    # Document processing - file extensions and keywords
    "pdf": [r"\.pdf\b", r"\bpdf\b", r"pdf file", r"pdf document", r"extract.*pdf"],
    # NOTE: Avoid matching generic "word" (e.g., "10,000 word article")
    # which caused false positives.
    "docx": [
        r"\.docx?\b",
        r"\bword document\b",
        r"\bms word\b",
        r"\bword file\b",
    ],
    "xlsx": [r"\.xlsx?\b", r"\bexcel\b", r"spreadsheet", r"\.xls\b", r"workbook"],
    "pptx": [r"\.pptx?\b", r"\bpowerpoint\b", r"presentation", r"\.ppt\b", r"slide"],
    # Data analysis
    "csv-data-summarizer": [r"\.csv\b", r"csv file", r"analyze.*data", r"data analysis", r"summarize.*csv"],
    # Creative & design
    "canvas-design": [r"create.*poster", r"design.*poster", r"design.*graphic", r"visual.*design", r"infographic", r"design.*banner"],
    "image-enhancer": [r"enhance.*(image|screenshot)", r"improve.*(image|screenshot)", r"upscale", r"sharpen", r"image quality", r"screenshot quality"],
    "image-generation": [r"generate.*image", r"create.*image", r"draw.*image", r"make.*picture", r"create.*diagram", r"generate.*illustration", r"ai.*image", r"image.*of\b"],
    # Methodology skills
    "brainstorming": [r"brainstorm", r"ideate", r"generate.*ideas", r"explore.*options", r"think.*through"],
    "root-cause-tracing": [r"root cause", r"trace.*error", r"debug.*chain", r"error.*chain", r"why.*fail"],
    "lead-research-assistant": [
        r"research.*company",
        r"lead.*research",
        r"competitive.*analysis",
        r"prospect",
        r"research.*topic",
        r"find.*information",
        r"look.*up",
        r"search.*for",
    ],
    "content-research-writer": [r"write.*article", r"research.*write", r"kb.*article", r"blog.*post", r"documentation"],
    # KB creator (existing)
    "kb-creator": [r"create.*kb", r"knowledge.*base", r"kb.*draft", r"support.*article"],
}


@dataclass
class SkillMetadata:
    """Metadata for a skill (progressive disclosure level 1)."""
    name: str
    description: str
    path: Path


@dataclass
class LoadedSkill:
    """Fully loaded skill with content and references (progressive disclosure level 2+)."""
    metadata: SkillMetadata
    content: str  # Full SKILL.md content
    references: dict[str, str]  # Additional reference files


class SkillsRegistry:
    """Registry for discovering and loading skills from .sparrow/skills/."""

    def __init__(self, project_root: Path | None = None):
        """
        Initialize the skills registry.

        Args:
            project_root: Path to project root. If None, auto-detects from this file's location.
        """
        # Find project root (contains .sparrow directory)
        if project_root is None:
            # app/agents/skills/__init__.py -> go up 4 levels to root
            project_root = Path(__file__).parent.parent.parent.parent

        self.project_root = project_root
        self.skills_dir = project_root / ".sparrow" / "skills"
        self._metadata_cache: dict[str, SkillMetadata] = {}
        self._loaded_cache: dict[str, LoadedSkill] = {}
        self._compiled_triggers: dict[str, list[Pattern[str]]] = self._compile_triggers()

        logger.debug(f"SkillsRegistry initialized with skills_dir: {self.skills_dir}")

    @staticmethod
    def _compile_triggers() -> dict[str, list[Pattern[str]]]:
        """Compile regex triggers once for reuse."""
        compiled: dict[str, list[Pattern[str]]] = {}
        for skill_name, patterns in SKILL_TRIGGERS.items():
            compiled[skill_name] = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        return compiled

    def discover_skills(self) -> list[SkillMetadata]:
        """
        Discover all available skills (metadata only - progressive disclosure level 1).

        Returns:
            List of SkillMetadata for all discovered skills.
        """
        skills = []
        if not self.skills_dir.exists():
            logger.warning(f"Skills directory not found: {self.skills_dir}")
            return skills

        for skill_dir in sorted(self.skills_dir.iterdir()):
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                try:
                    metadata = self._load_metadata(skill_dir)
                    if metadata:
                        skills.append(metadata)
                        self._metadata_cache[metadata.name] = metadata
                        logger.debug(f"Discovered skill: {metadata.name}")
                except Exception as e:
                    logger.error(f"Error loading skill metadata from {skill_dir}: {e}")

        logger.info(f"Discovered {len(skills)} skills: {[s.name for s in skills]}")
        return skills

    def _load_metadata(self, skill_dir: Path) -> Optional[SkillMetadata]:
        """
        Load only YAML frontmatter from SKILL.md (token efficient).

        Args:
            skill_dir: Path to the skill directory.

        Returns:
            SkillMetadata if valid frontmatter found, None otherwise.
        """
        skill_md = skill_dir / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")

        if content.startswith("---"):
            try:
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    data = yaml.safe_load(frontmatter)

                    if not data or "name" not in data or "description" not in data:
                        logger.warning(f"Invalid frontmatter in {skill_md}: missing name or description")
                        return None

                    return SkillMetadata(
                        name=data["name"],
                        description=data["description"],
                        path=skill_dir
                    )
            except yaml.YAMLError as e:
                logger.error(f"YAML parsing error in {skill_md}: {e}")
        else:
            logger.warning(f"No YAML frontmatter found in {skill_md}")

        return None

    def load_skill(self, name: str) -> Optional[LoadedSkill]:
        """
        Load full skill content (progressive disclosure level 2).

        Args:
            name: Name of the skill to load.

        Returns:
            LoadedSkill with full content and references, or None if not found.
        """
        if name in self._loaded_cache:
            return self._loaded_cache[name]

        metadata = self._metadata_cache.get(name)
        if not metadata:
            # Try discovering first
            self.discover_skills()
            metadata = self._metadata_cache.get(name)
            if not metadata:
                logger.warning(f"Skill not found: {name}")
                return None

        skill_md = metadata.path / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")

        # Load reference files (progressive disclosure level 3)
        references: dict[str, str] = {}
        ref_dir = metadata.path / "reference"
        if ref_dir.exists():
            for ref_file in ref_dir.glob("*.md"):
                try:
                    references[ref_file.stem] = ref_file.read_text(encoding="utf-8")
                    logger.debug(f"Loaded reference file: {ref_file.stem} for skill {name}")
                except Exception as e:
                    logger.error(f"Error loading reference file {ref_file}: {e}")

        skill = LoadedSkill(
            metadata=metadata,
            content=content,
            references=references
        )
        self._loaded_cache[name] = skill
        logger.info(f"Loaded skill: {name} with {len(references)} reference files")
        return skill

    def get_skills_prompt_section(self) -> str:
        """
        Generate skills metadata section for system prompt (~100 tokens per skill).

        Returns:
            Formatted string with available skills for injection into prompts.
        """
        skills = self.discover_skills()
        if not skills:
            return ""

        lines = ["## Available Skills", ""]
        for skill in skills:
            lines.append(f"- **{skill.name}**: {skill.description}")
        lines.append("")
        lines.append("To use a skill, read .sparrow/skills/{skill-name}/SKILL.md when relevant.")
        return "\n".join(lines)

    def should_activate_writing_skill(self, context: dict) -> bool:
        """
        Auto-detect when writing skill should be active.

        Args:
            context: Dictionary with context about the current operation.
                - is_final_response: Whether this is a final user-facing response
                - task_type: Type of task (e.g., "kb_creation", "support")
                - is_internal_call: Whether this is an internal tool/subagent call
                - is_zendesk_ticket: Whether this is a Zendesk ticket response

        Returns:
            True if writing skill should be activated.
        """
        # Activate for user-facing responses, KB articles, support content
        is_user_facing = context.get("is_final_response", False)
        is_kb_article = context.get("task_type") == "kb_creation"
        is_support_response = context.get("task_type") == "support"
        is_zendesk = context.get("is_zendesk_ticket", False)  # Explicit Zendesk check

        # Skip for internal tool calls, subagent research
        is_internal = context.get("is_internal_call", False)

        return (is_user_facing or is_kb_article or is_support_response or is_zendesk) and not is_internal

    def detect_skills_from_message(self, message: str) -> list[str]:
        """
        Detect which skills should be activated based on message content.

        Uses keyword pattern matching to identify relevant skills.
        Returns max 3 skills to avoid prompt bloat.

        Args:
            message: The user message to analyze.

        Returns:
            List of skill names that should be activated (max 3).
        """
        if not message:
            return []

        detected = []

        for skill_name, patterns in self._compiled_triggers.items():
            for pattern in patterns:
                if pattern.search(message):
                    if skill_name not in detected:
                        detected.append(skill_name)
                    break  # One match per skill is enough

        # Limit to 3 skills to avoid prompt bloat
        if len(detected) > 3:
            detected = detected[:3]
            logger.debug(f"Skill detection capped at 3: {detected}")

        if detected:
            logger.info(f"Auto-detected skills from message: {detected}")

        return detected

    def get_context_skills_content(self, context: dict) -> str:
        """
        Get skills content based on full context including message analysis.

        This is the main entry point for skill injection. It:
        1. Always injects writing/empathy for user-facing responses
        2. Auto-detects additional skills from message content
        3. Limits total skills to prevent prompt bloat

        Args:
            context: Dictionary with context about the current operation.
                - message: The user message (for auto-detection)
                - is_final_response: Whether this is a final user-facing response
                - task_type: Type of task
                - is_internal_call: Whether this is an internal tool/subagent call

        Returns:
            Combined skill content string to inject into prompt.
        """
        content_parts = []
        loaded_skills = set()

        # 1. Always inject writing/empathy for user-facing responses
        if self.should_activate_writing_skill(context):
            writing_skill = self.load_skill("writing")
            empathy_skill = self.load_skill("empathy")

            if writing_skill:
                content_parts.append(writing_skill.content)
                loaded_skills.add("writing")
            if empathy_skill:
                content_parts.append(empathy_skill.content)
                loaded_skills.add("empathy")

        # 2. Auto-detect skills from message (skip if internal call)
        message = context.get("message", "")
        is_internal = context.get("is_internal_call", False)

        if message and not is_internal:
            detected = self.detect_skills_from_message(message)

            for skill_name in detected:
                if skill_name not in loaded_skills:
                    skill = self.load_skill(skill_name)
                    if skill:
                        content_parts.append(skill.content)
                        loaded_skills.add(skill_name)

        if loaded_skills:
            logger.debug(f"Injected skills: {list(loaded_skills)}")

        return "\n\n".join(content_parts)

    def get_default_skills_content(self, context: dict) -> str:
        """
        Get default skills content based on context (writing + empathy for user-facing).

        DEPRECATED: Use get_context_skills_content() for full auto-detection.

        Args:
            context: Dictionary with context about the current operation.

        Returns:
            Combined skill content string to inject into prompt.
        """
        content_parts = []

        if self.should_activate_writing_skill(context):
            writing_skill = self.load_skill("writing")
            empathy_skill = self.load_skill("empathy")

            if writing_skill:
                content_parts.append(writing_skill.content)
            if empathy_skill:
                content_parts.append(empathy_skill.content)

        return "\n\n".join(content_parts)

    def clear_cache(self) -> None:
        """Clear all cached skills (useful for development/testing)."""
        self._metadata_cache.clear()
        self._loaded_cache.clear()
        logger.info("Skills cache cleared")


# Global registry instance (singleton pattern with thread safety consideration)
_registry: Optional[SkillsRegistry] = None
_registry_lock = None

try:
    import threading
    _registry_lock = threading.Lock()
except ImportError:
    pass


def get_skills_registry(project_root: Path | None = None) -> SkillsRegistry:
    """
    Get the global skills registry instance.

    Args:
        project_root: Optional project root path (only used on first call).

    Returns:
        The global SkillsRegistry instance.
    """
    global _registry

    if _registry is None:
        if _registry_lock:
            with _registry_lock:
                if _registry is None:
                    _registry = SkillsRegistry(project_root)
        else:
            _registry = SkillsRegistry(project_root)

    return _registry


def reset_skills_registry() -> None:
    """Reset the global skills registry (useful for testing)."""
    global _registry
    _registry = None


# Export public API
__all__ = [
    "SkillMetadata",
    "LoadedSkill",
    "SkillsRegistry",
    "get_skills_registry",
    "reset_skills_registry",
]
