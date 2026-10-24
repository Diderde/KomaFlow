"""③ Blender 适配层。"""

from .base import BlenderAdapter, BlenderInfo, VersionTuple
from .blender5 import Blender5Adapter
from .discovery import Candidate, describe_candidate, discover_blender
from .executor import ScriptOutcome, run_blender_script
from .registry import ADAPTERS, BASELINE, adapter_by_key, select_adapter

__all__ = [
    "BlenderAdapter",
    "BlenderInfo",
    "VersionTuple",
    "Blender5Adapter",
    "Candidate",
    "describe_candidate",
    "discover_blender",
    "ScriptOutcome",
    "run_blender_script",
    "ADAPTERS",
    "BASELINE",
    "adapter_by_key",
    "select_adapter",
]
