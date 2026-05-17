from copy import deepcopy
from typing import Dict, Optional

import tradingagents.default_config as default_config
from tradingagents.dataflows.massive import normalize_massive_provider_name

# Use default config but allow it to be overridden
_config: Optional[Dict] = None


def initialize_config():
    """Initialize the configuration with default values."""
    global _config
    if _config is None:
        _config = deepcopy(default_config.DEFAULT_CONFIG)


def _normalize_provider_chain(value):
    if not isinstance(value, str):
        return value

    providers = [part.strip() for part in value.split(",") if part.strip()]
    if not providers:
        return value
    return ",".join(normalize_massive_provider_name(provider) for provider in providers)


def _normalize_provider_config(config: Dict) -> Dict:
    normalized = deepcopy(config)
    for key in ("data_vendors", "tool_vendors"):
        vendor_map = normalized.get(key)
        if not isinstance(vendor_map, dict):
            continue
        normalized[key] = {
            method_or_category: _normalize_provider_chain(provider_chain)
            for method_or_category, provider_chain in vendor_map.items()
        }
    return normalized


def set_config(config: Dict):
    """Update the configuration with custom values.

    Dict-valued keys (e.g. ``data_vendors``) are merged one level deep so a
    partial update like ``{"data_vendors": {"core_stock_apis": "alpha_vantage"}}``
    keeps the other nested keys from the default; scalar keys are replaced.
    """
    global _config
    initialize_config()
    incoming = _normalize_provider_config(config)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(_config.get(key), dict):
            _config[key].update(value)
        else:
            _config[key] = value


def get_config() -> Dict:
    """Get the current configuration."""
    if _config is None:
        initialize_config()
    return deepcopy(_config)


# Initialize with default config
initialize_config()
