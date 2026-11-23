"""Progressive, token-efficient AoE2 knowledge retrieval.

Implements the kb-retriever pattern from garden-skills:
- Loads structured JSON files on demand (zero startup bloat).
- Retrieves precise build benchmarks, civ archetypes, and bonus damage math.
- Enriches coaching tips with verified numbers instead of generic advice.
"""
from __future__ import annotations

import json
import os

KNOWLEDGE_DIR = os.path.dirname(os.path.abspath(__file__))


class KnowledgeRetriever:
    def __init__(self, directory: str = KNOWLEDGE_DIR):
        self.directory = directory
        self._civs = None
        self._builds = None
        self._counters = None

    def _load(self, filename: str) -> dict:
        path = os.path.join(self.directory, filename)
        if not os.path.isfile(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @property
    def civs(self) -> dict:
        if self._civs is None:
            self._civs = self._load("civs.json")
        return self._civs

    @property
    def builds(self) -> dict:
        if self._builds is None:
            self._builds = self._load("build_orders.json")
        return self._builds

    @property
    def counters(self) -> dict:
        if self._counters is None:
            self._counters = self._load("counters.json")
        return self._counters

    def get_civ_info(self, civ_name: str) -> dict | None:
        if not civ_name:
            return None
        return self.civs.get(civ_name.strip().capitalize())

    def get_role_benchmarks(self, role: str) -> dict | None:
        role_lower = role.lower() if role else ""
        if "pocket" in role_lower:
            return self.builds.get("fast_castle_pocket")
        elif "archer" in role_lower or "flank" in role_lower:
            return self.builds.get("archer_rush_flank")
        return self.builds.get("scout_rush_flank")

    def get_counter_math(self, unit_category: str) -> dict | None:
        cat = unit_category.lower() if unit_category else ""
        if "cav" in cat or "knight" in cat:
            return self.counters.get("cavalry")
        elif "arch" in cat or "xbow" in cat:
            return self.counters.get("archers")
        elif "siege" in cat or "mango" in cat:
            return self.counters.get("siege")
        return self.counters.get("trash_wars")


# Global singleton instance
retriever = KnowledgeRetriever()
