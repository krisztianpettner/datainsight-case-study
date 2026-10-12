"""
Deep merge utility for Master/Delta schema resolution.

Merge rules:
- Scalars (str, int, float, bool): override wins
- Dicts: recursive merge (override keys win, base-only keys preserved)
- Lists: REPLACE (override list fully replaces base list, no append)

Based on: validators/schema_resolver.py:241-271
"""

import copy
from typing import Any, Dict


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries. Base is NOT modified.

    Args:
        base: Base dictionary (e.g. master schema)
        override: Override dictionary (e.g. delta schema)

    Returns:
        New merged dictionary
    """
    result = copy.deepcopy(base)

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            # Scalars and lists: override wins (lists = REPLACE, not append)
            result[key] = copy.deepcopy(value)

    return result
