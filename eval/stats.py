"""Wilson score interval."""
import math


def wilson(k, n, z=1.959964):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def show(k, n):
    low, high = wilson(k, n)
    return f'{k}/{n} = {100 * k / n:.1f}% (95% Wilson {100 * low:.1f}% to {100 * high:.1f}%)' if n else f'{k}/0'
