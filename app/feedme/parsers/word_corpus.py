"""
Word corpus management for OCR text validation.
Provides configurable word lists from JSON files and optional NLTK integration.
"""

import json
import logging
from pathlib import Path
from typing import Set, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)


class WordCorpusLoader:
    """Manages loading and caching of word corpora for text validation."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize word corpus loader.

        Args:
            config_path: Path to JSON configuration file. Defaults to common_words.json
        """
        if config_path is None:
            config_path = Path(__file__).parent / "common_words.json"

        self.config_path = config_path
        self._word_cache: Optional[Set[str]] = None
        self._nltk_available = self._check_nltk_availability()

    def _check_nltk_availability(self) -> bool:
        """Check if NLTK is available and properly configured."""
        try:
            from nltk.corpus import words  # type: ignore[import-untyped]

            # Try to access the words corpus
            try:
                words.words()[:10]  # Test access to first 10 words
                return True
            except LookupError:
                logger.warning(
                    "NLTK words corpus not downloaded. Falling back to config file."
                )
                return False

        except ImportError:
            logger.debug("NLTK not available. Using configuration file only.")
            return False

    @lru_cache(maxsize=1)
    def _load_config_words(self) -> Set[str]:
        """Load words from configuration file with caching."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Combine all word categories
            all_words = set()

            # Load common English words
            if "common_english_words" in config:
                all_words.update(config["common_english_words"])

            # Load technical words
            if "technical_words" in config:
                all_words.update(config["technical_words"])

            # Load email-specific words
            if "email_words" in config:
                all_words.update(config["email_words"])

            logger.info(f"Loaded {len(all_words)} words from configuration file")
            return all_words

        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.error(
                f"Failed to load word configuration from {self.config_path}: {e}"
            )
            # Return minimal fallback word set
            return {
                "the",
                "be",
                "to",
                "of",
                "and",
                "a",
                "in",
                "that",
                "have",
                "i",
                "it",
                "for",
                "not",
                "on",
                "with",
                "he",
                "as",
                "you",
                "do",
                "at",
                "email",
                "password",
                "login",
                "account",
                "user",
                "help",
                "error",
            }

    @lru_cache(maxsize=1)
    def _load_nltk_words(self) -> Set[str]:
        """Load words from NLTK corpus with caching."""
        if not self._nltk_available:
            return set()

        try:
            from nltk.corpus import words

            # Get English words from NLTK
            nltk_words = set(word.lower() for word in words.words() if word.isalpha())

            # Filter to reasonable length words (2-15 characters)
            filtered_words = {word for word in nltk_words if 2 <= len(word) <= 15}

            logger.info(f"Loaded {len(filtered_words)} words from NLTK corpus")
            return filtered_words

        except Exception as e:
            logger.error(f"Failed to load NLTK words: {e}")
            return set()

    def get_word_corpus(
        self, use_nltk: bool = True, min_word_length: int = 2
    ) -> Set[str]:
        """
        Get comprehensive word corpus for text validation.

        Args:
            use_nltk: Whether to include NLTK words if available
            min_word_length: Minimum word length to include

        Returns:
            Set of lowercase words for validation
        """
        if self._word_cache is not None:
            return self._word_cache

        # Start with configuration file words
        word_corpus = self._load_config_words()

        # Add NLTK words if requested and available
        if use_nltk and self._nltk_available:
            nltk_words = self._load_nltk_words()
            word_corpus.update(nltk_words)

        # Filter by minimum length
        if min_word_length > 1:
            word_corpus = {word for word in word_corpus if len(word) >= min_word_length}

        # Cache the result
        self._word_cache = word_corpus

        logger.info(f"Built word corpus with {len(word_corpus)} words")
        return word_corpus

    def is_valid_word(self, word: str, word_corpus: Optional[Set[str]] = None) -> bool:
        """
        Check if a word is valid using the corpus.

        Args:
            word: Word to validate
            word_corpus: Optional pre-loaded corpus, loads default if None

        Returns:
            True if word is valid
        """
        if word_corpus is None:
            word_corpus = self.get_word_corpus()

        word_lower = word.lower().strip()

        # Check if word is in corpus
        if word_lower in word_corpus:
            return True

        # Consider longer words (>4 chars) as potentially valid even if not in corpus
        if len(word_lower) > 4 and word_lower.isalpha():
            return True

        return False

    def reload_corpus(self):
        """Force reload of word corpus from sources."""
        # Clear caches
        self._load_config_words.cache_clear()
        self._load_nltk_words.cache_clear()
        self._word_cache = None

        # Recheck NLTK availability
        self._nltk_available = self._check_nltk_availability()

        logger.info("Word corpus reloaded")


# Global instance for convenient access
_default_loader = WordCorpusLoader()


def get_word_corpus(use_nltk: bool = True, min_word_length: int = 2) -> Set[str]:
    """Convenience function to get word corpus using default loader."""
    return _default_loader.get_word_corpus(
        use_nltk=use_nltk, min_word_length=min_word_length
    )


def is_valid_word(word: str) -> bool:
    """Convenience function to check word validity using default loader."""
    return _default_loader.is_valid_word(word)


def reload_word_corpus():
    """Convenience function to reload word corpus."""
    _default_loader.reload_corpus()
