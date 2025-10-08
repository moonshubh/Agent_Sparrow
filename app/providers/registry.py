from __future__ import annotations

import os
import sys
import json
import logging
import threading
from pathlib import Path
from typing import Dict, Tuple, Optional, Type
from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec

from .base import ProviderAdapter, BaseChatModel

logger = logging.getLogger(__name__)

# Thread-safe registry with RLock for concurrent access protection
_LOCK = threading.RLock()
_REGISTRY: Dict[Tuple[str, str], Type[ProviderAdapter]] = {}

# Configuration cache
_CONFIG_CACHE: Optional[Dict] = None
_BOOTSTRAPPED: bool = False


def _bootstrap_adapters() -> None:
    """Import the unified adapters package once to trigger registrations.

    Keeping this lazy avoids import cycles and keeps startup cost minimal while
    still allowing explicit adapter modules to self-register.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    try:
        # Import central adapters package; it imports known adapters guardedly
        # which call register_adapter() on import.
        import app.providers.adapters  # noqa: F401
    except Exception:
        # Adapters package is optional; fallback to file-based loader below
        pass
    finally:
        _BOOTSTRAPPED = True


def _load_config() -> Dict:
    """Load configuration from config.json with fallback to defaults."""
    global _CONFIG_CACHE

    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    config_path = Path(__file__).parent / "config.json"

    # Default configuration using naming convention
    default_config = {
        "provider_mappings": {
            "google": "Google",
            "openai": "OpenAI",
        },
        "model_mappings": {
            # Google
            "gemini-2.5-flash": "Gemini-2.5-Flash",
            # OpenAI (support multiple aliases)
            "gpt5-mini": "GPT-5-Mini",
            "gpt-5-mini": "GPT-5-Mini",
            "gpt-5-mini-2025-08-07": "GPT-5-Mini",
        }
    }

    try:
        if config_path.exists():
            with open(config_path, 'r') as f:
                _CONFIG_CACHE = json.load(f)
                logger.debug(f"Loaded provider configuration from {config_path}")
        else:
            _CONFIG_CACHE = default_config
            logger.debug("Using default provider configuration")
    except Exception as e:
        logger.warning(f"Failed to load config from {config_path}: {e}. Using defaults.")
        _CONFIG_CACHE = default_config

    return _CONFIG_CACHE


def register_adapter(provider: str, model: str, adapter_cls: Type[ProviderAdapter]):
    """Register an adapter for a provider/model combination."""
    with _LOCK:
        key = (provider.lower(), model.lower())
        _REGISTRY[key] = adapter_cls
        logger.debug(f"Registered adapter for {provider}/{model}")


def _ensure_loaded(provider: str, model: str) -> None:
    """
    Lazily import the adapter module for (provider, model) if it's not yet registered.
    We use file-based import to support hyphenated directory names, e.g. 'Gemini-2.5-Flash'.
    """
    with _LOCK:
        # First, attempt to bootstrap explicit registrations
        _bootstrap_adapters()

        key = (provider.lower(), model.lower())
        if key in _REGISTRY:
            return

        base_dir = os.path.dirname(__file__)
        config = _load_config()

        # Get mappings from configuration with fallback to naming convention
        provider_folder_map = config.get("provider_mappings", {})
        model_folder_map = config.get("model_mappings", {})

        # Fallback to naming convention if not in config
        provider_folder = provider_folder_map.get(
            provider.lower(),
            provider.title()  # Fallback: 'google' -> 'Google'
        )
        model_folder = model_folder_map.get(
            model.lower(),
            model.replace(" ", "-").title()  # Fallback: 'gpt 5 mini' -> 'Gpt-5-Mini'
        )
        if not provider_folder or not model_folder:
            logger.debug(f"No mapping found for provider={provider}, model={model}")
            return

        adapter_path = os.path.join(base_dir, provider_folder, model_folder, "adapter.py")
        if not os.path.exists(adapter_path):
            logger.debug(f"Adapter file not found at {adapter_path}")
            return

        module_name = f"app.providers.{provider_folder}.{model_folder}.adapter"
        # Load module by path (hyphenated dirs are fine with file loader)
        loader = SourceFileLoader(module_name, adapter_path)
        spec = spec_from_loader(module_name, loader)
        if spec is None:
            logger.warning(f"Failed to create module spec for {module_name}")
            return
        module = module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            loader.exec_module(module)  # type: ignore[attr-defined]
            logger.debug(f"Successfully loaded adapter module {module_name}")
        except Exception as e:
            # Log the error instead of silently failing
            logger.error(f"Failed to load adapter module {module_name}: {e}")
            return


def get_adapter(provider: str, model: str) -> ProviderAdapter:
    """Get an adapter instance for the specified provider and model."""
    _ensure_loaded(provider, model)

    with _LOCK:
        key = (provider.lower(), model.lower())
        if key not in _REGISTRY:
            raise ValueError(f"No adapter registered for provider={provider}, model={model}")
        return _REGISTRY[key]()  # type: ignore[call-arg]


async def load_model(provider: str, model: str, *, api_key: Optional[str] = None, **kwargs) -> BaseChatModel:
    adapter = get_adapter(provider, model)
    return await adapter.load_model(api_key=api_key, **kwargs)


def default_provider() -> str:
    # Default provider via env; fall back to google
    return os.getenv("PRIMARY_AGENT_PROVIDER", "google")


def default_model_for_provider(provider: str) -> str:
    env_default = os.getenv("PRIMARY_AGENT_MODEL")
    if env_default:
        return env_default
    # Reasonable defaults
    if provider.lower() == "openai":
        return "gpt5-mini"
    return "gemini-2.5-flash-preview-09-2025"