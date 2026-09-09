"""Small statistical helpers for reporting validation results.

Validation samples here are in the low hundreds, so a bare percentage
overstates what was measured. Every rate we publish carries an interval.
"""
from __future__ import annotations

import math

# z for a two-sided 95% interval.
Z95 = 1.959963985


def wilson_interval(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion.

    Preferred over the normal approximation because it stays inside [0, 1] and
    behaves sensibly at the small n and extreme proportions (0%, 100%) that a
    few-hundred-row review pass routinely produces.
    """
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (centre - spread) / denom), min(1.0, (centre + spread) / denom))


def format_rate(successes: int, n: int, decimals: int = 1) -> str:
    """`83.4% (76.6–88.6%, n=175)` — a rate that shows its own precision."""
    if n <= 0:
        return "– (n=0)"
    lo, hi = wilson_interval(successes, n)
    return (f"{successes / n:.{decimals}%} "
            f"({lo:.{decimals}%}–{hi:.{decimals}%}, n={n})")


def margin_of_error(successes: int, n: int) -> float:
    """Half-width of the Wilson interval, in percentage points."""
    if n <= 0:
        return 100.0
    lo, hi = wilson_interval(successes, n)
    return (hi - lo) / 2 * 100
