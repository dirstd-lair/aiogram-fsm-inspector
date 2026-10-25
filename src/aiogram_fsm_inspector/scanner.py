from __future__ import annotations

import logging
from typing import Dict, List, Set, Type

from aiogram.fsm.state import State, StatesGroup

logger = logging.getLogger("aiogram_fsm_inspector.scanner")


class StateRegistry:
    """
    Introspects Python runtime to discover all declared StatesGroup subclasses
    and their states for autocomplete in the web UI.
    """

    def __init__(self) -> None:
        self._tree: Dict[str, List[str]] = {}

    def scan(self) -> Dict[str, List[str]]:
        """
        Recursively scans StatesGroup subclasses across the entire Python process.
        Returns:
            Dict[group_name, List[state_string]]
        """
        tree: Dict[str, List[str]] = {}
        visited: Set[Type[StatesGroup]] = set()
        stack: List[Type[StatesGroup]] = list(StatesGroup.__subclasses__())

        while stack:
            group_cls = stack.pop()
            if group_cls in visited:
                continue
            visited.add(group_cls)

            # Discover nested subclasses
            stack.extend(group_cls.__subclasses__())

            states: List[str] = []

            # 1. Check __all_states__ if populated by StatesGroupMeta
            if hasattr(group_cls, "__all_states__"):
                states = [
                    s.state
                    for s in group_cls.__all_states__
                    if isinstance(s, State) and s.state
                ]

            # 2. Fallback to attribute introspection
            if not states:
                for attr_name in dir(group_cls):
                    if attr_name.startswith("_"):
                        continue
                    try:
                        val = getattr(group_cls, attr_name, None)
                        if isinstance(val, State) and val.state:
                            states.append(val.state)
                    except Exception:
                        continue

            if states:
                # Deduplicate while preserving declaration order
                unique_states = list(dict.fromkeys(states))
                tree[group_cls.__name__] = unique_states

        self._tree = tree
        logger.debug("Discovered %d StatesGroups with states: %s", len(tree), list(tree.keys()))
        return tree

    def get_tree(self) -> Dict[str, List[str]]:
        """Returns the current state tree, executing a scan if empty."""
        if not self._tree:
            self.scan()
        return dict(self._tree)

    def get_all_states(self) -> List[str]:
        """Returns a flat list of all discovered state strings."""
        tree = self.get_tree()
        all_states: List[str] = []
        for states in tree.values():
            all_states.extend(states)
        return all_states
