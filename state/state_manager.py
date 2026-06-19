"""Canonical state manager import path.

The current implementation keeps backward compatibility with the older
`state.entity_state.StateManager` while that module still hosts WebShop legacy
helpers. New code should import StateManager from here.
"""

from state.entity_state import StateManager

__all__ = ["StateManager"]
