"""언어 독립 난수 (SplitMix64) — Python · Rust · C# 가 같은 씨앗에서 같은 수열을 만든다.

명세: spec/SPEC.md §1
"""

from __future__ import annotations

import math

import numpy as np

_MASK = (1 << 64) - 1


class SpecRNG:
    def __init__(self, seed: int) -> None:
        self.state = seed & _MASK

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & _MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK
        return z ^ (z >> 31)

    def random(self) -> float:
        """[0, 1) 균등, 53비트."""
        return (self.next_u64() >> 11) * (1.0 / (1 << 53))

    def uniform(self, low: float, high: float, size=None):
        """low + (high-low)·u. size 가 있으면 행 우선(row-major) 순서로 채운 배열."""
        if size is None:
            return low + (high - low) * self.random()
        n = int(np.prod(size))
        u = np.fromiter((self.random() for _ in range(n)), dtype=float, count=n).reshape(size)
        return low + (high - low) * u

    def poisson(self, lam: float, size: int) -> np.ndarray:
        """Knuth 방식 (명세 §1.3)."""
        limit = math.exp(-lam)
        out = np.empty(size, dtype=int)
        for i in range(size):
            k, p = 0, 1.0
            while True:
                p *= self.random()
                if p <= limit:
                    break
                k += 1
            out[i] = k
        return out


def round_half_up(v: float) -> int:
    """명세의 반올림: floor(v + 0.5) (언어마다 다른 round 규칙을 피함)."""
    return int(math.floor(v + 0.5))
