"""Career Twin Core — the user-state centre shared by every skill.

Only deterministic code lives here: validation, versioning, provenance, state
machines, context assembly. Interpretation stays in the orchestrating agent.
"""
from __future__ import annotations

from . import actions, assertions, context, goals, pipeline, reflection, signals, twin

__all__ = ["actions", "assertions", "context", "goals", "pipeline", "reflection", "signals", "twin"]
