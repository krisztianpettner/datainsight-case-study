"""
Schema package - YAML-based schema registry for Tier 2 pipeline.

Provides:
- deep_merge: Deep merge utility for Master/Delta schema resolution
- FileSchemaRegistry: File-based YAML schema loader and compiler
"""

from parsing.schemas.merge import deep_merge
from parsing.schemas.registry import FileSchemaRegistry

__all__ = ["deep_merge", "FileSchemaRegistry"]
