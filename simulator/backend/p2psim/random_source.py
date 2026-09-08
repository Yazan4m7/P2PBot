from __future__ import annotations

import hashlib
import random


class DeterministicRandom:
    """Derives independent deterministic PRNG streams without global random state."""

    def __init__(self, seed: int):
        self.seed = int(seed)

    def stream(self, scope: str) -> random.Random:
        digest = hashlib.sha256(f"{self.seed}:{scope}".encode("utf-8")).digest()
        child_seed = int.from_bytes(digest[:16], "big", signed=False)
        return random.Random(child_seed)

    def decision_float(self, scope: str) -> float:
        return self.stream(scope).random()
